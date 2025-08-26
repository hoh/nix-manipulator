from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List, Optional

from tree_sitter import Node

from nix_manipulator.exceptions import NixSyntaxError
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.format import _format_trivia


class AttributeSet(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"attrset_expression"}
    values: List[Binding | Inherit]
    multiline: bool = True
    recursive: bool = False

    @classmethod
    def from_dict(cls, values: Dict[str, NixExpression]):
        from nix_manipulator.expressions.binding import Binding

        values_list: List[Binding | Inherit] = []
        for key, value in values.items():
            values_list.append(Binding(name=key, value=value))
        return cls(values=values_list)

    @classmethod
    def from_cst(cls, node: Node) -> AttributeSet:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        if node.text is None:
            raise ValueError("Attribute set has no code")

        from nix_manipulator.expressions.binding import Binding

        multiline = b"\n" in node.text
        values: list[Binding | Inherit] = []
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

        # Flatten content: unwrap `binding_set` if present
        content_nodes: list[Node] = []
        for child in node.named_children:
            if child.type == "binding_set":
                content_nodes.extend(child.named_children)
            else:
                content_nodes.append(child)

        prev_content: Optional[Node] = None
        for child in content_nodes:
            if child.type in (
                "binding",
                "comment",
                "variable_expression",
                "inherit",
                "string_fragment",
            ):
                push_gap(prev_content, child)

                if child.type == "binding":
                    values.append(Binding.from_cst(child, before=before))
                    before = []
                elif child.type == "comment":
                    comment = Comment.from_cst(child)
                    # Inline only when comment shares the *same row* as the binding terminator
                    inline_to_prev = (
                        prev_content is not None
                        and prev_content.type == "binding"
                        and child.start_point.row == prev_content.end_point.row
                        and values
                    )
                    if inline_to_prev:
                        values[-1].after.append(
                            comment
                        )  # attach to the *after*-trivia of that binding
                    else:
                        before.append(comment)
                elif child.type == "inherit":
                    values.append(Inherit.from_cst(child, before=before))
                    before = []
                elif child.type == "variable_expression":
                    # variable_expression – a function call
                    values.append(FunctionCall.from_cst(child, before=before))
                    before = []
                elif child.type == "string_fragment":
                    # Used by the function call called with the previous child
                    pass
                else:
                    raise ValueError(f"Unsupported child node: {child} {child.type}")

                prev_content = child
            elif child.type == "ERROR":
                raise NixSyntaxError(f"Code contains ERROR node: {child}")
            else:
                raise ValueError(f"Unsupported attrset child: {child.type}")

        # Attach dangling trivia to the last binding
        if before and values:
            values[-1].after.extend(before)

        return cls(values=values, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2

        if not self.values:
            # return f"{before_str}{{ }}{after_str}"
            return self.add_trivia("{ }", indent=indent, inline=inline)

        if self.multiline:
            before_str = _format_trivia(self.before, indent=indented)
            after_str = _format_trivia(self.after, indent=indented)
            bindings_str = "\n".join(
                [value.rebuild(indent=indented, inline=False) for value in self.values]
            )
            return (
                f"{before_str}{{"
                + f"\n{bindings_str}\n"
                + " " * indent
                + f"}}{after_str}"
            )
        else:
            bindings_str = " ".join(
                [value.rebuild(indent=indented, inline=True) for value in self.values]
            )
            return self.add_trivia(
                f"{{ {bindings_str} }}", indent=indent, inline=inline
            )

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


class RecursiveAttributeSet(AttributeSet):
    tree_sitter_types: ClassVar[set[str]] = {"rec_attrset_expression"}
    values: List[Binding | Inherit]
    multiline: bool = True
    recursive: bool = True


__all__ = ["AttributeSet", "RecursiveAttributeSet"]
