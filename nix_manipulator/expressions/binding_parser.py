"""Helpers for parsing binding and inherit sequences without circular imports."""

from __future__ import annotations

from typing import Any

from tree_sitter import Node

from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.trivia import parse_delimited_sequence


def parse_binding_sequence(
    parent: Node,
    content_nodes: list[Node],
    *,
    initial_trivia: list[Any] | None = None,
    open_token: str | None = None,
    close_token: str | None = None,
) -> tuple[list[Binding | Inherit], list[Any]]:
    """Parse binding/inherit sequences with consistent inline-comment handling."""

    def parse_item(child: Node, before_trivia: list[Any]) -> Binding | Inherit:
        """Normalize bindings/inherits to avoid invalid members."""
        if child.type == "binding":
            return Binding.from_cst(child, before=before_trivia)
        if child.type in ("inherit", "inherit_from"):
            return Inherit.from_cst(child, before=before_trivia)
        raise ValueError(f"Unsupported child node: {child} {child.type}")

    def can_inline_comment(prev: Node | None, comment_node: Node, items: list) -> bool:
        """Inline only when comments share a line with the preceding item."""
        return (
            prev is not None
            and prev.type in ("binding", "inherit", "inherit_from")
            and comment_node.start_point.row == prev.end_point.row
            and bool(items)
        )

    def attach_inline_comment(item: NixExpression, comment: Comment) -> None:
        """Attach inline comments to keep binding formatting intact."""
        item.after.append(comment)

    return parse_delimited_sequence(
        parent,
        content_nodes,
        open_token=open_token,
        close_token=close_token,
        parse_item=parse_item,
        can_inline_comment=can_inline_comment,
        attach_inline_comment=attach_inline_comment,
        initial_trivia=initial_trivia,
    )


__all__ = ["parse_binding_sequence"]
