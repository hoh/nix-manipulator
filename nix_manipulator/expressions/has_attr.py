"""Has-attribute expressions with preserved operator spacing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.trivia import (
    collect_comments_between_with_gap,
    format_interstitial_trivia_with_separator,
    layout_from_gap,
)


@dataclass(slots=True, repr=False)
class HasAttrExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"has_attr_expression"}
    expression: NixExpression
    attrpath: str
    left_gap: str = " "
    right_gap: str = " "
    before_question_comments: list[Any] = field(default_factory=list)
    after_question_comments: list[Any] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node) -> HasAttrExpression:
        """Capture spacing/comments around `?` so attribute checks round-trip faithfully."""
        if node.text is None:
            raise ValueError("Missing has-attr expression")

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        expression_node = node.child_by_field_name("expression")
        attrpath_node = node.child_by_field_name("attrpath")

        if expression_node is None or attrpath_node is None:
            raise ValueError("Missing has-attr expression fields")
        if attrpath_node.text is None:
            raise ValueError("Missing has-attr attrpath text")

        question_node = next(
            (child for child in node.children if child.type == "?"), None
        )

        comment_nodes = [child for child in node.children if child.type == "comment"]
        left_gap = " "
        right_gap = " "
        before_question_comments: list[Any] = []
        after_question_comments: list[Any] = []
        if question_node is not None:
            (
                before_question_comments,
                left_gap,
            ) = collect_comments_between_with_gap(
                node,
                comment_nodes,
                expression_node,
                question_node,
                allow_inline=True,
            )
            (
                after_question_comments,
                right_gap,
            ) = collect_comments_between_with_gap(
                node,
                comment_nodes,
                question_node,
                attrpath_node,
                allow_inline=True,
            )

        return cls(
            expression=tree_sitter_node_to_expression(expression_node),
            attrpath=attrpath_node.text.decode(),
            left_gap=left_gap,
            right_gap=right_gap,
            before_question_comments=before_question_comments,
            after_question_comments=after_question_comments,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct has-attr expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        expression_str = self.expression.rebuild(indent=indent, inline=True)

        left_layout = layout_from_gap(self.left_gap)
        right_layout = layout_from_gap(self.right_gap)

        if self.before_question_comments:
            left_layout = left_layout.model_copy(update={"blank_line": False})
        if self.after_question_comments:
            right_layout = right_layout.model_copy(update={"blank_line": False})

        force_left_newline = any(
            isinstance(item, Comment) or item in (linebreak, empty_line)
            for item in self.before_question_comments
        )
        if force_left_newline and not left_layout.on_newline:
            left_layout = left_layout.model_copy(
                update={
                    "on_newline": True,
                    "blank_line": any(
                        item is empty_line for item in self.before_question_comments
                    ),
                }
            )

        force_right_newline = any(
            isinstance(item, Comment) or item in (linebreak, empty_line)
            for item in self.after_question_comments
        )
        if force_right_newline and not right_layout.on_newline:
            right_layout = right_layout.model_copy(
                update={
                    "on_newline": True,
                    "blank_line": any(
                        item is empty_line for item in self.after_question_comments
                    ),
                }
            )

        before_question_str, left_sep = format_interstitial_trivia_with_separator(
            self.before_question_comments,
            left_layout,
            indent=indent,
            drop_blank_line_if_items=False,
        )
        after_question_str, right_sep = format_interstitial_trivia_with_separator(
            self.after_question_comments,
            right_layout,
            indent=indent,
            drop_blank_line_if_items=False,
        )

        rebuild_string = (
            f"{expression_str}{before_question_str}{left_sep}?"
            f"{after_question_str}{right_sep}{self.attrpath}"
        )
        return self.add_trivia(rebuild_string, indent, inline)


__all__ = ["HasAttrExpression"]
