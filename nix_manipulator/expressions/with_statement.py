"""With expressions that preserve spacing between environment and body."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.indented_string import IndentedString
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.trivia import (
    append_gap_trivia, collect_comments_between_with_gap,
    format_inline_comment_suffix, format_interstitial_trivia_with_separator,
    layout_from_gap, split_inline_comments, trim_leading_layout_trivia)


@dataclass(slots=True, repr=False)
class WithStatement(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"with_expression"}
    environment: NixExpression
    body: NixExpression
    after_with_comments: list[Any] = field(default_factory=list)
    after_with_gap: str = " "
    after_semicolon_comments: list[Any] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node):
        """Preserve spacing/comments around `with` so scope formatting survives edits."""
        if node.text is None:
            raise ValueError("Missing text in with statement")

        environment_node = node.child_by_field_name("environment")
        body_node = node.child_by_field_name("body")
        with_node = next((child for child in node.children if child.type == "with"), None)
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        environment = tree_sitter_node_to_expression(environment_node)
        body = tree_sitter_node_to_expression(body_node)

        after_with_comments: list[Any] = []
        after_with_gap: str = " "
        after_semicolon_comments: list[Any] = []
        comment_nodes = [child for child in node.children if child.type == "comment"]

        if with_node is not None and environment_node is not None:
            after_with_comments, after_with_gap = collect_comments_between_with_gap(
                node,
                comment_nodes,
                with_node,
                environment_node,
                allow_inline=True,
            )

        if environment_node is not None and body_node is not None:
            between_comments, trailing_gap = collect_comments_between_with_gap(
                node,
                comment_nodes,
                environment_node,
                body_node,
                allow_inline=True,
            )
            if not between_comments:
                append_gap_trivia(between_comments, trailing_gap)
            if between_comments:
                remaining_comments, inline_comments = split_inline_comments(
                    between_comments
                )
                if inline_comments:
                    after_semicolon_comments.extend(inline_comments)
                if remaining_comments:
                    body.before = remaining_comments + body.before

        return cls(
            environment=environment,
            body=body,
            after_with_comments=after_with_comments,
            after_with_gap=after_with_gap,
            after_semicolon_comments=after_semicolon_comments,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct with expression while honoring captured trivia gaps."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        after_with_layout = layout_from_gap(self.after_with_gap)
        if self.after_with_comments:
            after_with_layout = after_with_layout.model_copy(update={"blank_line": False})
        force_env_newline = any(
            item in (linebreak, empty_line)
            or (isinstance(item, Comment) and not item.inline)
            for item in self.after_with_comments
        )
        if force_env_newline and not after_with_layout.on_newline:
            after_with_layout = after_with_layout.model_copy(
                update={
                    "on_newline": True,
                    "blank_line": any(item is empty_line for item in self.after_with_comments),
                }
            )

        environment_expr = self.environment
        if after_with_layout.on_newline:
            trimmed_before = trim_leading_layout_trivia(environment_expr.before)
            if trimmed_before != environment_expr.before:
                environment_expr = environment_expr.model_copy(
                    update={"before": trimmed_before}
                )
            env_indent = (
                after_with_layout.indent
                if after_with_layout.indent is not None
                else indent
            )
            environment_str = environment_expr.rebuild(
                indent=env_indent, inline=False
            )
        else:
            environment_str = environment_expr.rebuild(indent=indent, inline=True)
        after_with_comments_str, env_prefix = (
            format_interstitial_trivia_with_separator(
                self.after_with_comments,
                after_with_layout,
                indent=indent,
                include_indent=False,
                drop_blank_line_if_items=False,
            )
        )

        def is_absorbable_term(expr: NixExpression) -> bool:
            """Return True for RFC absorbable terms (lists, sets, indented strings)."""
            if isinstance(expr, Parenthesis):
                return is_absorbable_term(expr.value)
            if isinstance(expr, NixList):
                if expr.multiline is None and len(expr.value) > 1:
                    return False
                return True
            return isinstance(expr, (AttributeSet, IndentedString))

        def body_prefers_newline(expr: NixExpression) -> bool:
            """Prefer newline when constructed lists need multiline output."""
            if isinstance(expr, Parenthesis):
                return body_prefers_newline(expr.value)
            if isinstance(expr, NixList):
                return expr.multiline is None and len(expr.value) > 1
            return False

        body_force_newline = (
            bool(self.after_with_comments)
            or bool(self.after_semicolon_comments)
            or body_prefers_newline(self.body)
            or any(
                item in (linebreak, empty_line) or isinstance(item, Comment)
                for item in self.body.before
            )
        )

        if not body_force_newline and is_absorbable_term(self.body):
            body_str = self.body.rebuild(indent=indent, inline=False)
            body_sep = " "
            if body_sep == " " and indent:
                indent_prefix = " " * indent
                if body_str.startswith(indent_prefix):
                    body_str = body_str[len(indent_prefix):]
        else:
            inline_body = self.body.rebuild(indent=indent, inline=True)
            if body_force_newline or "\n" in inline_body:
                body_sep = "\n"
                body_str = self.body.rebuild(indent=indent, inline=False)
            else:
                body_sep = " "
                body_str = inline_body

        semicolon_comment_str = format_inline_comment_suffix(
            self.after_semicolon_comments
        )

        rebuild_string = (
            f"with{after_with_comments_str}{env_prefix}{environment_str};"
            f"{semicolon_comment_str}{body_sep}{body_str}"
        )
        return self.add_trivia(rebuild_string, indent=indent, inline=inline)

    def _attach_body_context(self) -> NixExpression:
        """Ensure the body carries the with-environment scope."""
        from nix_manipulator.resolution import attach_resolution_context

        attach_resolution_context(self.body, owner=self)
        return self.body

    def __getitem__(self, key: str):
        """Delegate lookups to the body after attaching resolution context."""
        body = self._attach_body_context()
        if hasattr(body, "__getitem__"):
            return body[key]  # type: ignore[index]
        raise TypeError("WithStatement body does not support item access")


__all__ = ["WithStatement"]
