"""Parenthesized expressions with preserved inner whitespace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.trivia import (
    gap_between, gap_has_empty_line_from_offsets, layout_from_gap,
    parse_delimited_sequence)


@dataclass(slots=True)
class Parenthesis(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"parenthesized_expression"}
    value: NixExpression
    leading_gap: str = ""
    trailing_gap: str = ""
    leading_blank_line: bool = False
    trailing_blank_line: bool = False

    @classmethod
    def from_cst(cls, node: Node) -> Parenthesis:
        """Capture inner spacing so parentheses round-trip without changes."""
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.text is None:
            raise ValueError("Parenthesis has no code")

        open_paren = next((child for child in node.children if child.type == "("), None)
        close_paren = next((child for child in reversed(node.children) if child.type == ")"), None)
        if open_paren is None or close_paren is None:
            raise ValueError("Parenthesis is missing delimiters")

        value: NixExpression | None = None
        value_node: Node | None = None

        content_nodes = [child for child in node.children if child.type not in ("(", ")")]
        first_content = content_nodes[0] if content_nodes else None
        last_content = content_nodes[-1] if content_nodes else None

        def parse_item(child: Node, before_trivia: list[Any]):
            """Capture the single inner expression with its leading trivia."""
            nonlocal value, value_node
            if value is not None:
                raise ValueError("Parenthesis contains multiple expressions")
            value_node = child
            value = tree_sitter_node_to_expression(child)
            if before_trivia:
                value.before = before_trivia + value.before
            return value

        def can_inline_comment(
            prev: Node | None, comment_node: Node, items: list
        ) -> bool:
            """Allow inline comments only when they stay on the same line."""
            return (
                prev is not None
                and comment_node.start_point.row == prev.end_point.row
                and bool(items)
            )

        def attach_inline_comment(item: NixExpression, comment: Comment) -> None:
            """Attach inline comments to the inner expression for fidelity."""
            item.after.append(comment)

        parse_delimited_sequence(
            node,
            content_nodes,
            parse_item=parse_item,
            can_inline_comment=can_inline_comment,
            attach_inline_comment=attach_inline_comment,
        )

        if value is None or value_node is None:
            raise ValueError("Parenthesis contains no expression")

        gap_before = gap_between(node, open_paren, value_node)
        gap_after = gap_between(node, value_node, close_paren)
        leading_blank_line = False
        trailing_blank_line = False
        if first_content is not None:
            leading_blank_line = gap_has_empty_line_from_offsets(
                node, open_paren.end_byte, first_content.start_byte
            )
        if last_content is not None:
            trailing_blank_line = gap_has_empty_line_from_offsets(
                node, last_content.end_byte, close_paren.start_byte
            )

        return cls(
            value=value,
            leading_gap=gap_before,
            trailing_gap=gap_after,
            leading_blank_line=leading_blank_line,
            trailing_blank_line=trailing_blank_line,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        leading_layout = layout_from_gap(self.leading_gap).model_copy(
            update={"blank_line": self.leading_blank_line}
        )
        trailing_layout = layout_from_gap(self.trailing_gap).model_copy(
            update={"blank_line": self.trailing_blank_line}
        )
        multiline = leading_layout.on_newline or trailing_layout.on_newline
        indentation = " " * indent if multiline else ("" if inline else " " * indent)

        if multiline:
            if leading_layout.on_newline:
                inner_indent = (
                    leading_layout.indent
                    if leading_layout.indent is not None
                    else indent + 2
                )
                inner = self.value.rebuild(indent=inner_indent, inline=False)
                prefix = "\n\n" if leading_layout.blank_line else "\n"
                inner = prefix + inner
            else:
                inner_indent = indent
                inner = self.value.rebuild(indent=inner_indent, inline=True)
            if trailing_layout.on_newline:
                suffix = "\n\n" if trailing_layout.blank_line else "\n"
                inner = inner + suffix + indentation
            return self.add_trivia(f"({inner})", indent, inline)

        value_str = f"({self.value.rebuild(indent=indent, inline=True)})"
        return self.add_trivia(value_str, indent, inline)

    def __repr__(self):
        """Expose nested value for debugging formatting decisions."""
        return f"Parenthesis(\nvalue={self.value}\n)"


__all__ = ["Parenthesis"]
