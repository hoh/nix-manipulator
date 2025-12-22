"""Assertion expressions that preserve spacing and inline comments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.trivia import (
    Layout, append_gap_trivia, collect_comments_between_with_gap,
    format_interstitial_trivia_with_separator, gap_has_empty_line,
    split_inline_comments, trim_leading_layout_trivia)


@dataclass(slots=True)
class Assertion(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "assert_expression",
    }
    expression: NixExpression
    body: NixExpression | None = None
    between: list[Any] = field(default_factory=list)
    after_assert_comments: list[Any] = field(default_factory=list)
    before_semicolon_comments: list[Any] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node, before: list[Any] | None = None):
        """Capture assertion layout/comments so condition/body spacing stays intact."""
        if node.text is None:
            raise ValueError("Identifier has no name")

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        condition_node = node.child_by_field_name("condition")
        if condition_node is None or condition_node.text is None:
            raise ValueError("Assertion has no condition")
        condition = tree_sitter_node_to_expression(condition_node)
        assert_node = next(
            (child for child in node.children if child.type == "assert"), None
        )
        body_node = node.child_by_field_name("body")
        if body_node is None:
            raise ValueError("Assertion has no body")

        body = tree_sitter_node_to_expression(body_node)

        semicolon_node = next(
            (child for child in node.children if child.type == ";"), None
        )
        comment_nodes = [
            child for child in node.children if child.type == "comment"
        ]
        after_assert_comments: list[Any] = []
        before_semicolon_comments: list[Any] = []
        if assert_node is not None and condition_node is not None:
            after_assert_comments, trailing_gap = (
                collect_comments_between_with_gap(
                    node,
                    comment_nodes,
                    assert_node,
                    condition_node,
                    allow_inline=True,
                )
            )
            if not after_assert_comments:
                append_gap_trivia(after_assert_comments, trailing_gap)
            elif "\n" in trailing_gap and not gap_has_empty_line(trailing_gap):
                after_assert_comments.append(linebreak)
        if semicolon_node is not None and condition_node is not None:
            before_semicolon_comments, _ = (
                collect_comments_between_with_gap(
                    node,
                    comment_nodes,
                    condition_node,
                    semicolon_node,
                    allow_inline=True,
                )
            )
        start_node = semicolon_node if semicolon_node is not None else condition_node
        between, trailing_gap = collect_comments_between_with_gap(
            node,
            comment_nodes,
            start_node,
            body_node,
            allow_inline=semicolon_node is not None,
        )
        if not between and gap_has_empty_line(trailing_gap):
            between.append(empty_line)
        after_assert_trailing: list[Any] = []
        if between and semicolon_node is not None:
            between, after_assert_trailing = split_inline_comments(between)

        assertion = cls(
            expression=condition,
            body=body,
            between=between,
            before=before or [],
            after_assert_comments=after_assert_comments,
            before_semicolon_comments=before_semicolon_comments,
        )
        if after_assert_trailing:
            assertion.after.extend(after_assert_trailing)
        return assertion

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct assertion while keeping comment-adjacent gaps intact."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        def trivia_forces_newline(items: list[Any]) -> bool:
            """Detect trivia that mandates a line break before the condition."""
            for item in items:
                if item in (linebreak, empty_line):
                    return True
                if isinstance(item, Comment) and not item.inline:
                    return True
            return False

        def inline_is_absorbed(rendered: str) -> bool:
            """Allow multiline conditions if only inner lines are indented."""
            lines = rendered.splitlines()
            if len(lines) <= 1:
                return True
            for line in lines[1:-1]:
                if line.strip() and not line.startswith(" "):
                    return False
            return True

        condition_inline = self.expression.rebuild(indent=indent, inline=True)
        condition_absorbed = inline_is_absorbed(condition_inline)
        condition_on_newline = (
            trivia_forces_newline(self.after_assert_comments)
            or not condition_absorbed
        )
        condition_expr = self.expression
        if condition_on_newline:
            trimmed_before = trim_leading_layout_trivia(condition_expr.before)
            if trimmed_before != condition_expr.before:
                condition_expr = condition_expr.model_copy(
                    update={"before": trimmed_before}
                )
            condition_indent = indent + 2
            condition_str = condition_expr.rebuild(
                indent=condition_indent, inline=False
            )
        else:
            condition_indent = indent
            condition_str = condition_inline

        condition_layout = Layout(
            on_newline=condition_on_newline,
            blank_line=False,
            indent=condition_indent if condition_on_newline else None,
        )
        after_assert_comments_str, condition_prefix = (
            format_interstitial_trivia_with_separator(
                self.after_assert_comments,
                condition_layout,
                indent=condition_indent,
                include_indent=False,
                strip_leading_newline_after=condition_str,
            )
        )
        semicolon_inline_sep = " " if self.before_semicolon_comments else ""
        if self.before_semicolon_comments:
            semicolon_layout = Layout(
                on_newline=True,
                blank_line=False,
                indent=indent,
            )
            before_semicolon_comments_str, semicolon_prefix = (
                format_interstitial_trivia_with_separator(
                    self.before_semicolon_comments,
                    semicolon_layout,
                    indent=indent,
                    inline_sep=semicolon_inline_sep,
                    strip_leading_newline_after=condition_str,
                )
            )
        else:
            before_semicolon_comments_str = ""
            semicolon_prefix = ""

        core = (
            f"assert{after_assert_comments_str}{condition_prefix}{condition_str}"
            f"{before_semicolon_comments_str}{semicolon_prefix};"
        )
        assert_line = self.add_trivia(core, indent, inline)

        if self.body is None:
            return assert_line

        body_expr = self.body
        if self.between:
            body_expr = body_expr.model_copy()
            body_expr.before = list(self.between) + list(body_expr.before)
        body_str = body_expr.rebuild(indent=indent, inline=False)
        separator = "" if assert_line.endswith("\n") else "\n"
        return f"{assert_line}{separator}{body_str}"


__all__ = ["Assertion"]
