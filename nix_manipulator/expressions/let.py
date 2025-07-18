from __future__ import annotations

import re
from typing import Any, ClassVar, List, Optional

from tree_sitter import Node

from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.format import _format_trivia


class LetExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"let_expression"}
    local_variables: List[Binding | Inherit]
    value: NixExpression
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node) -> LetExpression:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        if node.text is None:
            raise ValueError("Attribute set has no code")

        from nix_manipulator.expressions import Comment, empty_line, linebreak
        from nix_manipulator.expressions.binding import Binding
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        before: list[Any] = []

        def push_gap(prev: Optional[Node], cur: Node) -> None:
            """Detect an empty line between *prev* and *cur*."""
            if prev is None:
                return
            start = prev.end_byte - node.start_byte
            end = cur.start_byte - node.start_byte
            gap = node.text[start:end].decode()
            if re.search(r"\n[ \t]*\n", gap):
                before.append(empty_line)
            elif "\n" in gap:  # exactly one line-break — keep it
                before.append(linebreak)

        multiline = b"\n" in node.text

        let_symbol: Node
        in_symbol: Node
        binding_set: Node
        for child in node.children:
            if child.type == "let":
                let_symbol = child
            elif child.type == "in":
                in_symbol = child
            elif child.type == "binding_set":
                binding_set = child
            elif child.type == "comment":
                before.append(child)
            else:
                pass

        children_types = [child.type for child in node.children]

        value: NixExpression = tree_sitter_node_to_expression(node.children[-1])

        local_variables: list[Binding | Inherit] = []
        prev_content: Optional[Node] = None
        for child in binding_set.children:
            push_gap(prev_content, child)
            child_expression: NixExpression = tree_sitter_node_to_expression(child)
            if isinstance(child_expression, Comment):
                before.append(child_expression)
            elif isinstance(child_expression, Binding):
                child_expression.before = before
                local_variables.append(child_expression)
                before = []
            else:
                raise ValueError(f"Unsupported child node: {child} {child.type}")
            prev_content = child

        if before:
            local_variables[-1].after.extend(before)

        pregap = node.text[
            let_symbol.end_byte : binding_set.children[0].start_byte
        ].decode()
        if re.search(r"\n[ \t]*\n", pregap):
            local_variables[0].before.insert(0, empty_line)

        postgap = node.text[
            binding_set.children[-1].end_byte : in_symbol.start_byte
        ].decode()
        if re.search(r"\n[ \t]*\n", postgap):
            local_variables[-1].after.append(empty_line)

        return cls(local_variables=local_variables, value=value, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2
        indentation = "" if inline else " " * indented

        if self.multiline:
            before_str = _format_trivia(self.before, indent=indented)
            after_str = _format_trivia(self.after, indent=indented)
            bindings_str = "\n".join(
                [
                    var.rebuild(indent=indented, inline=False)
                    for var in self.local_variables
                ]
            )
            return (
                f"{before_str}"
                + " " * indent
                + f"let"
                + f"\n{bindings_str}\n"
                + " " * indent
                + "in\n"
                + self.value.rebuild(indent=indent, inline=False)
                + f"{after_str}"
            )
        else:
            raise NotImplementedError

    def __getitem__(self, key: str):
        for variable in self.local_variables:
            if isinstance(variable, Binding):
                if variable.name == key:
                    return variable.value
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        for i, variable in enumerate(self.local_variables):
            if isinstance(variable, Binding):
                if variable.name == key:
                    variable.value = value
                    return
        self.local_variables.append(Binding(name=key, value=value))

    def __delitem__(self, key: str):
        for i, variable in enumerate(self.local_variables):
            if isinstance(variable, Binding) and variable.name == key:
                del self.local_variables[i]


__all__ = ["LetExpression"]
