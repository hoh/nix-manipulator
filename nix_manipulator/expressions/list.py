"""List expression parsing and formatting with whitespace preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (
    NixExpression,
    TypedExpression,
    coerce_expression,
)
from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.trivia import (
    apply_trailing_trivia,
    format_trivia,
    gap_has_empty_line_from_offsets,
    parse_delimited_sequence,
)

MAX_INLINE_LIST_WIDTH = 100


def process_list(node: Node):
    """Parse a list node into values and inner trivia."""
    from nix_manipulator.mapping import tree_sitter_node_to_expression

    content_nodes = [child for child in node.children if child.type not in ("[", "]")]

    def parse_item(child: Node, before_trivia: list[Any]) -> NixExpression:
        """Attach leading trivia so list items retain spacing."""
        child_expression: NixExpression = tree_sitter_node_to_expression(child)
        child_expression.before = before_trivia
        return child_expression

    def can_inline_comment(prev: Node | None, comment_node: Node, items: list) -> bool:
        """Allow inline comments only when they remain on the same line."""
        return (
            prev is not None
            and comment_node.start_point.row == prev.end_point.row
            and bool(items)
        )

    def attach_inline_comment(item: NixExpression, comment: Comment) -> None:
        """Attach inline comments to the preceding list element."""
        item.after.append(comment)

    values, inner_trivia = parse_delimited_sequence(
        node,
        content_nodes,
        open_token="[",
        close_token="]",
        parse_item=parse_item,
        can_inline_comment=can_inline_comment,
        attach_inline_comment=attach_inline_comment,
    )

    return values, inner_trivia


@dataclass(slots=True, repr=False)
class NixList(TypedExpression):
    """Nix list expression that preserves original multiline structure."""

    tree_sitter_types: ClassVar[set[str]] = {"list_expression"}
    value: list[NixExpression | str | int | bool | float | None] = field(
        default_factory=list
    )
    multiline: bool | None = None
    inner_trivia: list[Any] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node):
        """Parse list content while retaining whitespace and comment trivia."""
        node_text = node.text
        if node_text is None:
            raise ValueError("List has no code")

        multiline = b"\n" in node_text
        value, inner_trivia = process_list(node)
        if not value and not inner_trivia:
            opening_bracket = next(
                (child for child in node.children if child.type == "["), None
            )
            closing_bracket = next(
                (child for child in node.children if child.type == "]"), None
            )
            if opening_bracket is not None and closing_bracket is not None:
                if gap_has_empty_line_from_offsets(
                    node, opening_bracket.end_byte, closing_bracket.start_byte
                ):
                    inner_trivia = [empty_line]

        return cls(
            value=value,
            multiline=multiline,
            inner_trivia=inner_trivia,
        )

    def _item_requires_multiline(self, expr: NixExpression) -> bool:
        """Detect items that force multiline output to preserve readability."""
        if expr.before or expr.after:
            return True
        inline_render = expr.rebuild(indent=0, inline=True)
        return "\n" in inline_render

    def _auto_multiline(
        self, *, indent: int, inline: bool, respect_existing: bool = True
    ) -> bool:
        """Infer multiline layout to avoid collapsing meaningful spacing."""
        if respect_existing and self.multiline is not None:
            return self.multiline

        if not self.value:
            return bool(self.inner_trivia)
        if self.inner_trivia:
            return True

        for item in self.value:
            expr = coerce_expression(item)
            if self._item_requires_multiline(expr):
                return True

        count = len(self.value)
        if inline and indent == 0:
            return count > 2
        return count > 1

    def _inline_preview(self, *, indent: int) -> str:
        """Generate a compact inline version for list call formatting."""
        if not self.value:
            return "[ ]"
        items = [
            coerce_expression(item).rebuild(indent=indent, inline=True)
            for item in self.value
        ]
        return f"[ {' '.join(items)} ]"

    def simple_inline_preview(
        self, *, indent: int, max_width: int = MAX_INLINE_LIST_WIDTH
    ) -> str | None:
        """Offer a safe inline preview for callers that need compact output."""
        if self.multiline:
            return None
        if self.before or self.after or self.inner_trivia:
            return None
        if len(self.value) > 1:
            return None
        preview = self._inline_preview(indent=indent)
        if "\n" in preview or len(preview) > max_width:
            return None
        return preview

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct list."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        before_str = format_trivia(self.before, indent=indent)
        multiline = self._auto_multiline(indent=indent, inline=inline)
        indented = indent + 2 if multiline else indent
        indentation = "" if inline else " " * indented

        if not self.value:
            if self.inner_trivia:
                inner_str = format_trivia(self.inner_trivia, indent=indent + 2)
                closing_sep = ""
                if inner_str:
                    closing_sep = "" if inner_str.endswith("\n") else "\n"
                indentation = "" if inline else " " * indent
                list_str = (
                    f"{before_str}{indentation}[\n{inner_str}{closing_sep}"
                    + " " * indent
                    + "]"
                )
                return apply_trailing_trivia(list_str, self.after, indent=indent)
            indentor = "" if inline else " " * indent
            list_str = f"{indentor}[ ]"
            return apply_trailing_trivia(
                f"{before_str}{list_str}", self.after, indent=indent
            )

        def render_item(item: NixExpression | str | int | bool | float | None) -> str:
            """Render list items consistently based on multiline decision."""
            expr = coerce_expression(item)
            return expr.rebuild(indent=indented, inline=not multiline)

        items = [render_item(item) for item in self.value]

        if multiline:
            # Add proper indentation for multiline lists
            items_str = "\n".join(items)
            indentor = "" if inline else (" " * indent)
            closing_sep = "" if items_str.endswith("\n") else "\n"
            list_str = indentor + f"[\n{items_str}{closing_sep}" + " " * indent + "]"
        else:
            items_str = " ".join(items)
            indentor = "" if inline else " " * indent
            list_str = f"{indentor}[ {items_str} ]"

        return apply_trailing_trivia(
            f"{before_str}{list_str}", self.after, indent=indent
        )


__all__ = ["NixList"]
