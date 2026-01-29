"""Bindings inside attribute sets, preserving spacing and trivia."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, cast

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (
    NixExpression,
    TypedExpression,
    coerce_expression,
)
from nix_manipulator.expressions.layout import linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.scope import ScopeState
from nix_manipulator.expressions.trivia import (
    append_gap_trivia_from_offsets,
    apply_trailing_trivia,
    format_trivia,
    gap_between,
    layout_from_gap,
)


def _split_attrpath(text: str) -> list[str]:
    """Split an attrpath into segments, respecting quotes and interpolations."""
    segments: list[str] = []
    buffer: list[str] = []
    in_quotes = False
    escape = False
    interp_depth = 0
    interp_in_quotes = False
    interp_escape = False

    index = 0
    while index < len(text):
        ch = text[index]
        if interp_depth > 0:
            buffer.append(ch)
            if interp_in_quotes:
                if interp_escape:
                    interp_escape = False
                elif ch == "\\":
                    interp_escape = True
                elif ch == '"':
                    interp_in_quotes = False
            else:
                if ch == '"':
                    interp_in_quotes = True
                elif ch == "{":
                    interp_depth += 1
                elif ch == "}":
                    interp_depth -= 1
            index += 1
            continue

        if in_quotes:
            if not escape and ch == "$" and index + 1 < len(text):
                if text[index + 1] == "{":
                    buffer.append(ch)
                    buffer.append("{")
                    interp_depth = 1
                    index += 2
                    continue
            buffer.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_quotes = False
            index += 1
            continue

        if ch == '"':
            in_quotes = True
            buffer.append(ch)
            index += 1
            continue
        if ch == "$" and index + 1 < len(text) and text[index + 1] == "{":
            buffer.append(ch)
            buffer.append("{")
            interp_depth = 1
            index += 2
            continue
        if ch == ".":
            segment = "".join(buffer).strip()
            if not segment:
                raise ValueError("Empty attrpath segment")
            segments.append(segment)
            buffer = []
            index += 1
            continue
        buffer.append(ch)
        index += 1

    if interp_depth > 0:
        raise ValueError("Unterminated attrpath interpolation")
    if in_quotes:
        raise ValueError("Unterminated quoted attrpath segment")

    segment = "".join(buffer).strip()
    if not segment:
        raise ValueError("Empty attrpath segment")
    segments.append(segment)
    return segments


@dataclass(slots=True, repr=False)
class Binding(TypedExpression):
    """Single `name = value;` binding with preserved trivia."""

    tree_sitter_types: ClassVar[set[str]] = {"binding"}
    name: str
    value: NixExpression | str | int | bool | float | None | list[Any] | dict[str, Any]
    value_gap: str = " "
    nested: bool = field(default=False, compare=False)

    def __post_init__(self) -> None:
        """Normalize dict payloads into attribute sets."""
        NixExpression.__post_init__(self)
        if isinstance(self.value, dict):
            from nix_manipulator.expressions.set import AttributeSet

            self.value = AttributeSet.from_dict(self.value)

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ):
        """Capture binding layout to preserve spacing, comments, and alignment."""
        if node.text is None:
            raise ValueError("Binding has no code")

        before = before or []
        after = after or []

        children = (
            node.children[0].children if len(node.children) == 1 else node.children
        )

        name: str | None = None
        value: Any | None = None
        value_node: Node | None = None

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        before_value: list[Any] = []
        equals_token: Node | None = None
        prev_content: Node | None = None

        def push_gap(prev: Node | None, cur: Node) -> None:
            """Track whitespace to preserve layout between binding tokens."""
            if prev is None:
                return
            append_gap_trivia_from_offsets(
                before_value, node, prev.end_byte, cur.start_byte
            )

        for child in children:
            if child.type in ("=", ";"):
                if child.type == "=":
                    equals_token = child
                prev_content = child
                continue
            elif child.text and child.type == "attrpath":
                name = child.text.decode()
                prev_content = child
            elif child.type == "comment":
                comment = Comment.from_cst(child)
                if (
                    value_node is not None
                    and prev_content == value_node
                    and child.start_point.row == value_node.end_point.row
                    and isinstance(value, NixExpression)
                ):
                    comment.inline = True
                    value.after.append(comment)
                    prev_content = child
                    continue
                push_gap(prev_content, child)
                before_value.append(comment)
                prev_content = child
            else:
                push_gap(prev_content, child)
                value = tree_sitter_node_to_expression(child)
                value_node = child
                if before_value:
                    value.before = before_value + value.before
                    before_value = []
                prev_content = child

        if name is None or value is None:
            raise ValueError("Could not parse binding")

        if before_value:
            value.after.extend(before_value)

        value_gap = " "
        if equals_token is not None and value_node is not None:
            value_gap = gap_between(node, equals_token, value_node)

        segments = _split_attrpath(name)
        if len(segments) > 1:
            from nix_manipulator.expressions.set import AttributeSet

            leaf = cls._fast_construct(
                name=segments[-1],
                value=value,
                before=before,
                after=after,
                scope=[],
                scope_state=ScopeState(),
                value_gap=value_gap,
            )
            current: Binding = cast(Binding, leaf)
            for index, segment in enumerate(reversed(segments[:-1])):
                nested = AttributeSet(values=[current])
                is_root = index == len(segments[:-1]) - 1
                if is_root:
                    current = cls(
                        name=segment,
                        value=nested,
                        nested=True,
                        before=list(before),
                        after=list(after),
                    )
                else:
                    current = cls(
                        name=segment,
                        value=nested,
                        nested=True,
                        before=[linebreak],
                        after=[linebreak],
                    )
            return current

        return cls._fast_construct(
            name=name,
            value=value,
            before=before,
            after=after,
            scope=[],
            scope_state=ScopeState(),
            value_gap=value_gap,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:  # noqa: C901
        """Reconstruct binding while honoring captured semicolon placement."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        before_str = format_trivia(self.before, indent=indent)
        indentation = "" if inline else " " * indent

        # Decide how the *value* itself has to be rendered
        value_layout = layout_from_gap(self.value_gap)
        if value_layout.on_newline:
            val_indent = (
                value_layout.indent if value_layout.indent is not None else indent + 2
            )
        else:
            val_indent = indent

        value_expr = coerce_expression(self.value)
        value_after = list(value_expr.after)
        if value_after:
            value_expr = value_expr.model_copy(update={"after": []})
        if not value_layout.on_newline and any(
            isinstance(item, Comment) for item in value_expr.before
        ):
            value_layout = value_layout.model_copy(
                update={"on_newline": True, "blank_line": False, "indent": None}
            )
            val_indent = indent + 2

        def render_value(expr: NixExpression) -> str:
            """Select inline or multiline rendering to mirror original intent."""
            if not value_layout.on_newline:
                if isinstance(expr, NixList):
                    inline_preview = expr.simple_inline_preview(indent=val_indent)
                    if inline_preview is not None:
                        return inline_preview
            return expr.rebuild(indent=val_indent, inline=not value_layout.on_newline)

        value_str = render_value(value_expr)
        if value_str.endswith("\n"):
            value_str = value_str.rstrip("\n")

        # Assemble left-hand side
        sep = "\n" if value_layout.on_newline else " "
        core = f"{self.name} ={sep}{value_str}"

        core = f"{core};"

        rebuilt = f"{before_str}{indentation}{core}"

        after_items = value_after + self.after
        if after_items and after_items[0] is linebreak:
            # Preserve an explicit linebreak marker even though it formats as "".
            trailing = format_trivia(after_items[1:], indent=indent)
            if not trailing.startswith("\n"):
                trailing = "\n" + trailing
            if trailing.endswith("\n"):
                trailing = trailing[:-1]
            return f"{rebuilt}{trailing}"

        return apply_trailing_trivia(rebuilt, after_items, indent=indent)


__all__ = ["Binding"]
