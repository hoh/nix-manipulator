"""Select expressions with preserved spacing rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.trivia import (
    collect_comments_between_with_gap,
    format_interstitial_trivia_with_separator,
    format_trivia,
    layout_from_gap,
)


@dataclass(slots=True, repr=False)
class Select(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"select_expression"}
    expression: NixExpression
    attribute: str
    default: NixExpression | None = None
    attr_gap: str = ""
    attr_before: list[Any] = field(default_factory=list)
    default_gap: str = " "
    default_before: list[Any] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node) -> Select:
        """Capture attrpath/default spacing so selection rebuilds cleanly."""
        if node.text is None:
            raise ValueError("Select expression is missing")
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        expression_node = node.child_by_field_name("expression")
        attrpath_node = node.child_by_field_name("attrpath")
        default_node = node.child_by_field_name("default")

        if expression_node is None or attrpath_node is None:
            raise ValueError("Select expression is missing required fields")
        if attrpath_node.text is None:
            raise ValueError("Select expression attrpath is missing")

        comment_nodes = [child for child in node.children if child.type == "comment"]
        dot_node = next((child for child in node.children if child.type == "."), None)
        attr_gap = ""
        attr_before: list[Any] = []
        if dot_node is not None:
            attr_before, attr_gap = collect_comments_between_with_gap(
                node,
                comment_nodes,
                expression_node,
                dot_node,
                allow_inline=True,
            )

        default_gap = " "
        default_before: list[Any] = []
        if default_node is not None:
            or_node = next(
                (child for child in node.children if child.type == "or"), None
            )
            boundary_node = or_node if or_node is not None else default_node
            if boundary_node is not None:
                default_before, default_gap = collect_comments_between_with_gap(
                    node,
                    comment_nodes,
                    attrpath_node,
                    boundary_node,
                    allow_inline=True,
                )
        return cls(
            expression=tree_sitter_node_to_expression(expression_node),
            attribute=attrpath_node.text.decode(),
            default=(
                tree_sitter_node_to_expression(default_node)
                if default_node is not None
                else None
            ),
            attr_gap=attr_gap,
            attr_before=attr_before,
            default_gap=default_gap,
            default_before=default_before,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct select expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        expression_str = self.expression.rebuild(indent=indent, inline=True)
        attr_layout = layout_from_gap(self.attr_gap)
        if self.attr_before:
            attr_layout = attr_layout.model_copy(update={"blank_line": False})
        attr_indent = (
            attr_layout.indent
            if attr_layout.on_newline and attr_layout.indent is not None
            else indent
        )
        attr_before_str, attr_sep = format_interstitial_trivia_with_separator(
            self.attr_before,
            attr_layout,
            indent=attr_indent,
            drop_blank_line_if_items=False,
            inline_sep="",
            strip_leading_newline_after=expression_str,
        )
        if expression_str.endswith("\n") and attr_sep.startswith("\n"):
            attr_sep = attr_sep[1:]
        rebuild_string = f"{expression_str}{attr_before_str}{attr_sep}.{self.attribute}"
        if self.default is not None:
            default_layout = layout_from_gap(self.default_gap)
            if default_layout.on_newline:
                default_indent = (
                    default_layout.indent
                    if default_layout.indent is not None
                    else indent + 2
                )
                default_sep = "\n\n" if default_layout.blank_line else "\n"
                default_str = self.default.rebuild(indent=default_indent, inline=True)
                default_before = list(self.default_before)
                inline_comment = ""
                if default_before:
                    first = default_before[0]
                    if isinstance(first, Comment) and first.inline:
                        inline_comment = f" {first.rebuild(indent=0)}"
                        default_before = default_before[1:]
                rebuild_string = f"{rebuild_string}{inline_comment}"
                comment_str = (
                    format_trivia(default_before, indent=default_indent)
                    if default_before
                    else ""
                )
                or_indent = " " * default_indent if default_indent else ""
                if comment_str:
                    if not comment_str.endswith("\n"):
                        comment_str += "\n"
                    rebuild_string = (
                        f"{rebuild_string}{default_sep}{comment_str}"
                        f"{or_indent}or {default_str}"
                    )
                else:
                    rebuild_string = (
                        f"{rebuild_string}{default_sep}{or_indent}or {default_str}"
                    )
            else:
                default_str = self.default.rebuild(indent=indent, inline=True)
                rebuild_string = f"{rebuild_string} or {default_str}"
        return self.add_trivia(rebuild_string, indent, inline)


__all__ = ["Select"]
