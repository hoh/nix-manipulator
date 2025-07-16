from __future__ import annotations

from typing import Any, ClassVar, List, Optional

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.format import _format_trivia


class FunctionCall(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"apply_expression"}
    name: str
    argument: Optional[NixExpression] = None
    recursive: bool = False
    multiline: bool = True

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        multiline = b"\n" in node.text

        if not node.text:
            raise ValueError("Missing function name")
        name = node.child_by_field_name("function").text.decode()

        recursive = (
            node.child_by_field_name("argument").type == "rec_attrset_expression"
        )

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        argument = tree_sitter_node_to_expression(node.child_by_field_name("argument"))

        return cls(
            name=name,
            argument=argument,
            recursive=recursive,
            multiline=multiline,
            before=before or [],
            after=after or [],
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function call."""
        indented = indent + 2
        before_str = _format_trivia(self.before, indent=indented)
        after_str = _format_trivia(self.after, indent=indented)
        indentation = "" if inline else " " * indent

        if not self.argument:
            return f"{before_str}{indentation}{self.name}{after_str}"

        args_str = self.argument.rebuild(
            indent=indent, inline=inline or (not self.multiline)
        )

        rec_str = " rec" if self.recursive else ""
        return f"{before_str}{indentation}{self.name}{rec_str} {args_str}{after_str}"


__all__ = ["FunctionCall"]
