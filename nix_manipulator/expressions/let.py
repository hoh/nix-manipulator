from __future__ import annotations

from typing import Any, ClassVar, List

from tree_sitter import Node

from nix_manipulator.expressions import Comment
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.format import _format_trivia


class LetExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"let_expression"}
    local_variables: List[Binding | Inherit | FunctionCall]
    value: NixExpression
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node) -> LetExpression:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        from nix_manipulator.expressions.binding import Binding
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        multiline = b"\n" in node.text

        children_types = [child.type for child in node.children]

        assert children_types[:3] == ["let", "binding_set", "in"], f"Invalid let expression {children_types}"

        binding_set = node.children[1]
        value: NixExpression = tree_sitter_node_to_expression(node.children[-1])

        local_variables: list[Binding | Inherit] = []
        before: list[Any] = []
        for child in binding_set.children:
            if child.type == "comment":
                before.append(Comment.from_cst(child))
                continue
            assert child.type in ("binding",), f"Unsupported child node: {child} {child.type}"
            local_variables.append(Binding.from_cst(child, before=before))
            before = []

        if before:
            local_variables[-1].after.extend(before)

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
        for binding in self.values:
            if binding.name == key:
                return binding.value
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        for i, binding in enumerate(self.values):
            if binding.name == key:
                binding.value = value
                return
        self.values.append(Binding(name=key, value=value))

    def __delitem__(self, key: str):
        for i, binding in enumerate(self.values):
            if binding.name == key:
                del self.values[i]


__all__ = ["LetExpression"]
