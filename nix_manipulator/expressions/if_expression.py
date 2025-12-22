"""If/then/else expressions with whitespace-aware formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.trivia import (
    collect_comments_between_with_gap, format_inline_comment_suffix,
    format_interstitial_trivia_with_separator, gap_between, layout_from_gap,
    split_inline_comments)


@dataclass(slots=True)
class IfExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"if_expression",}
    condition: NixExpression
    consequence: NixExpression
    alternative: NixExpression
    condition_gap: str = " "
    after_if_comments: list[Any] = field(default_factory=list)
    after_if_gap: str = " "
    before_then_comments: list[Any] = field(default_factory=list)
    after_then_comments: list[Any] = field(default_factory=list)
    before_then_gap: str = " "
    then_gap: str = " "
    before_else_gap: str = " "
    before_else_comments: list[Any] = field(default_factory=list)
    after_else_comments: list[Any] = field(default_factory=list)
    else_gap: str = " "

    @classmethod
    def from_cst(cls, node: Node) -> IfExpression:
        """Capture spacing/comments around if/then/else to preserve intent."""
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if_node = None
        then_node = None
        else_node = None
        for child in node.children:
            if child.type == "if":
                if_node = child
            elif child.type == "then":
                then_node = child
            elif child.type == "else":
                else_node = child

        condition = node.child_by_field_name("condition")
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")

        condition_gap = ""
        if if_node is not None and condition is not None:
            condition_gap = gap_between(node, if_node, condition)

        then_gap = ""
        before_else_gap = ""
        else_gap = ""
        if then_node is not None and consequence is not None:
            then_gap = gap_between(node, then_node, consequence)
        if else_node is not None and alternative is not None:
            else_gap = gap_between(node, else_node, alternative)

        comment_nodes = [child for child in node.children if child.type == "comment"]

        after_if_comments: list[Any] = []
        after_if_gap = ""
        if if_node is not None and condition is not None:
            after_if_comments, after_if_gap = collect_comments_between_with_gap(
                node,
                comment_nodes,
                if_node,
                condition,
                allow_inline=True,
            )

        consequence_expr = tree_sitter_node_to_expression(consequence)
        alternative_expr = tree_sitter_node_to_expression(alternative)

        then_comments: list[Any] = []
        after_then_comments: list[Any] = []
        else_comments: list[Any] = []
        after_else_comments: list[Any] = []
        if then_node is not None and consequence is not None:
            then_comments, _ = collect_comments_between_with_gap(
                node,
                comment_nodes,
                then_node,
                consequence,
                allow_inline=True,
            )
            if then_comments:
                remaining_then_comments, inline_comments = split_inline_comments(
                    then_comments
                )
                after_then_comments.extend(inline_comments)
                if remaining_then_comments:
                    consequence_expr.before = (
                        remaining_then_comments + consequence_expr.before
                    )

        if else_node is not None and alternative is not None:
            else_comments, _ = collect_comments_between_with_gap(
                node,
                comment_nodes,
                else_node,
                alternative,
                allow_inline=True,
            )
            if else_comments:
                remaining_else_comments, inline_comments = split_inline_comments(
                    else_comments
                )
                after_else_comments.extend(inline_comments)
                if remaining_else_comments:
                    alternative_expr.before = (
                        remaining_else_comments + alternative_expr.before
                    )

        before_then_comments: list[Any] = []
        before_then_gap = ""
        if then_node is not None and condition is not None:
            before_then_comments, before_then_gap = (
                collect_comments_between_with_gap(
                    node,
                    comment_nodes,
                    condition,
                    then_node,
                    allow_inline=True,
                )
            )

        before_else_comments: list[Any] = []
        if else_node is not None and consequence is not None:
            before_else_comments, before_else_gap = (
                collect_comments_between_with_gap(
                    node,
                    comment_nodes,
                    consequence,
                    else_node,
                    allow_inline=True,
                )
            )

        return cls(
            condition=tree_sitter_node_to_expression(condition),
            consequence=consequence_expr,
            alternative=alternative_expr,
            condition_gap=condition_gap,
            after_if_comments=after_if_comments,
            after_if_gap=after_if_gap,
            before_then_comments=before_then_comments,
            after_then_comments=after_then_comments,
            before_then_gap=before_then_gap,
            then_gap=then_gap,
            before_else_gap=before_else_gap,
            before_else_comments=before_else_comments,
            after_else_comments=after_else_comments,
            else_gap=else_gap,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        def layout_without_blank_line(
            layout, *, has_comments: bool
        ):
            """Drop blank-line intent when comments occupy the gap."""
            if has_comments:
                return layout.model_copy(update={"blank_line": False})
            return layout

        def render_branch(expr: NixExpression, layout) -> tuple[str, str]:
            """Render then/else branches with consistent spacing rules."""
            if layout.on_newline:
                sep = "\n\n" if layout.blank_line else "\n"
                branch_indent = (
                    layout.indent if layout.indent is not None else indent
                )
                return sep, expr.rebuild(indent=branch_indent, inline=False)
            return " ", expr.rebuild(indent=indent, inline=True)

        condition_layout = layout_from_gap(self.condition_gap)
        after_if_layout = layout_without_blank_line(
            layout_from_gap(self.after_if_gap),
            has_comments=bool(self.after_if_comments),
        )
        before_then_layout = layout_without_blank_line(
            layout_from_gap(self.before_then_gap),
            has_comments=bool(self.before_then_comments),
        )
        has_then_comments = bool(self.after_then_comments) or any(
            isinstance(item, Comment) for item in self.consequence.before
        )
        then_layout = layout_without_blank_line(
            layout_from_gap(self.then_gap),
            has_comments=has_then_comments,
        )
        before_else_layout = layout_without_blank_line(
            layout_from_gap(self.before_else_gap),
            has_comments=bool(self.before_else_comments),
        )
        has_else_comments = bool(self.after_else_comments) or any(
            isinstance(item, Comment) for item in self.alternative.before
        )
        else_layout = layout_without_blank_line(
            layout_from_gap(self.else_gap),
            has_comments=has_else_comments,
        )

        if condition_layout.on_newline:
            condition_indent = (
                condition_layout.indent
                if condition_layout.indent is not None
                else indent
            )
            condition_str = self.condition.rebuild(
                indent=condition_indent, inline=False
            )
        else:
            condition_indent = indent
            condition_str = self.condition.rebuild(indent=indent, inline=True)

        after_if_comments_str, condition_prefix = (
            format_interstitial_trivia_with_separator(
                self.after_if_comments,
                after_if_layout,
                indent=condition_indent,
                inline_comment_newline=True,
                include_indent=False,
                strip_leading_newline_after=condition_str,
                drop_blank_line_if_items=False,
            )
        )

        between_str, then_prefix = format_interstitial_trivia_with_separator(
            self.before_then_comments,
            before_then_layout,
            indent=indent,
            inline_comment_newline=True,
            strip_leading_newline_after=condition_str,
            drop_blank_line_if_items=False,
        )

        then_sep, then_str = render_branch(self.consequence, then_layout)

        before_else_comments_str, before_else_sep = (
            format_interstitial_trivia_with_separator(
                self.before_else_comments,
                before_else_layout,
                indent=indent,
                inline_comment_newline=True,
                strip_leading_newline_after=then_str,
                drop_blank_line_if_items=False,
            )
        )

        else_sep, else_str = render_branch(self.alternative, else_layout)

        after_then_str = format_inline_comment_suffix(self.after_then_comments)
        after_else_str = format_inline_comment_suffix(self.after_else_comments)

        rebuild_string = (
            f"if{after_if_comments_str}{condition_prefix}{condition_str}"
            f"{between_str}{then_prefix}then{after_then_str}{then_sep}{then_str}"
            f"{before_else_comments_str}{before_else_sep}else{after_else_str}{else_sep}{else_str}"
        )

        return self.add_trivia(rebuild_string, indent, inline)

    def __repr__(self):
        """Expose condition for debugging complex formatting paths."""
        return f"IfExpression(\nif={self.condition}\n)"


__all__ = ["IfExpression"]
