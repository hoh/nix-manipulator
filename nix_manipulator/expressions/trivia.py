"""Whitespace and trivia helpers used to preserve original Nix formatting."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable

from tree_sitter import Node

from nix_manipulator.expressions.layout import comma, empty_line, linebreak

_EMPTY_LINE_RE = re.compile(r"\n[ \t]*\n")
_GAP_WHITESPACE_BYTES = (32, 9)
_SOURCE_BYTES: ContextVar[bytes | None] = ContextVar(
    "nix_source_bytes", default=None
)


@contextmanager
def source_bytes_context(source_bytes: bytes | None):
    """Share source bytes to avoid repeated decoding across trivia helpers."""
    token = _SOURCE_BYTES.set(source_bytes)
    try:
        yield
    finally:
        _SOURCE_BYTES.reset(token)


def _gap_span(
    parent: Node, start_byte: int, end_byte: int
) -> tuple[bytes, int, int] | None:
    """Resolve a byte span for gap checks while tolerating missing text."""
    if start_byte == end_byte:
        return None
    source_bytes = _SOURCE_BYTES.get()
    if source_bytes is not None:
        return source_bytes, start_byte, end_byte
    if parent.text is None:
        return None
    base = parent.start_byte
    start = start_byte - base
    end = end_byte - base
    if start < 0 or end < 0:
        return None
    return parent.text, start, end


def _gap_line_info_from_offsets(
    parent: Node, start_byte: int, end_byte: int
) -> tuple[int, int | None]:
    """Count newlines and trailing indent bytes between offsets."""
    span = _gap_span(parent, start_byte, end_byte)
    if span is None:
        return 0, None
    source_bytes, start, end = span
    newline_count = source_bytes.count(b"\n", start, end)
    if newline_count == 0:
        return 0, None
    last_newline = source_bytes.rfind(b"\n", start, end)
    indent = end - last_newline - 1
    return newline_count, indent


def _gap_has_empty_line_offsets(
    source_bytes: bytes, start: int, end: int, first_newline: int | None = None
) -> bool:
    """Check for blank lines using offsets to avoid slice allocations."""
    if first_newline is None:
        first_newline = source_bytes.find(b"\n", start, end)
        if first_newline == -1:
            return False
    second_newline = source_bytes.find(b"\n", first_newline + 1, end)
    if second_newline == -1:
        return False
    newline_index = first_newline
    while newline_index != -1:
        cursor = newline_index + 1
        while cursor < end and source_bytes[cursor] in _GAP_WHITESPACE_BYTES:
            cursor += 1
        if cursor < end and source_bytes[cursor] == 10:
            return True
        newline_index = source_bytes.find(b"\n", cursor, end)
    return False


@dataclass(slots=True)
class Layout:
    """Capture newline/blank-line/indent layout metadata for a gap."""

    on_newline: bool = False
    blank_line: bool = False
    indent: int | None = None

    @classmethod
    def from_gap(cls, gap: str) -> "Layout":
        """Interpret gap strings so spacing decisions align with input."""
        if "\n" not in gap:
            return cls(on_newline=False, blank_line=False, indent=None)
        return cls(
            on_newline=True,
            blank_line=gap_has_empty_line(gap),
            indent=indent_from_gap(gap),
        )

    def with_indent(self, indent: int | None) -> "Layout":
        """Return a tweaked layout to reuse existing spacing rules."""
        return replace(self, indent=indent)

    def model_copy(self, update: dict[str, Any] | None = None) -> "Layout":
        """Clone layouts for safe mutation during formatting decisions."""
        if not update:
            return copy(self)
        return replace(self, **update)


def layout_from_gap(gap: str) -> Layout:
    """Convenience wrapper around Layout.from_gap (ignores non-RFC spacing)."""
    return Layout.from_gap(gap)


def separator_from_layout(
    layout: Layout, *, indent: int, inline_sep: str = " "
) -> str:
    """Render a gap separator from a layout, defaulting to inline_sep."""
    if not layout.on_newline:
        return inline_sep
    sep = "\n\n" if layout.blank_line else "\n"
    target_indent = layout.indent if layout.indent is not None else indent
    if target_indent:
        sep += " " * target_indent
    return sep


def separator_from_layout_with_comments(
    layout: Layout,
    comment_str: str,
    *,
    inline_sep: str = " ",
    include_indent: bool = True,
) -> str:
    """Render a separator after interstitial trivia based on a layout."""
    if layout.on_newline:
        sep = "" if comment_str.endswith("\n") else "\n"
        if layout.blank_line:
            sep += "\n"
        if include_indent and layout.indent:
            sep += " " * layout.indent
        return sep
    if comment_str:
        return "" if comment_str.endswith((" ", "\n")) else inline_sep
    return inline_sep


def format_trivia(trivia_list: list[Any], indent: int = 0) -> str:
    """Convert trivia objects to string representation."""
    if not trivia_list:
        return ""
    from nix_manipulator.expressions.assertion import Assertion
    from nix_manipulator.expressions.comment import Comment, MultilineComment

    parts: list[str] = []
    ends_with_newline = True
    indent_str = " " * indent if indent else ""
    for index, item in enumerate(trivia_list):
        if item is empty_line:
            parts.append("\n")
            ends_with_newline = True
        elif item is linebreak:
            continue
        elif item is comma:
            if not parts or ends_with_newline:
                if indent_str:
                    parts.append(indent_str)
                    ends_with_newline = False
            parts.append(",")
            ends_with_newline = False
            next_item = (
                trivia_list[index + 1] if index + 1 < len(trivia_list) else None
            )
            if isinstance(next_item, Comment) and next_item.inline:
                parts.append(" ")
                ends_with_newline = False
            elif next_item is linebreak or next_item is None:
                parts.append("\n")
                ends_with_newline = True
        elif isinstance(item, (Comment, MultilineComment, Assertion)):
            parts.append(item.rebuild(indent=indent))
            parts.append("\n")
            ends_with_newline = True
        else:
            raise NotImplementedError(f"Unsupported trivia item: {item}")
    return "".join(parts)


def format_interstitial_trivia(
    items: list[Any],
    *,
    indent: int,
    inline_comment_newline: bool = False,
) -> str:
    """Render interstitial trivia, optionally forcing inline comments onto newlines."""
    rendered = ""
    for item in items:
        if item is empty_line:
            if not rendered.endswith("\n"):
                rendered += "\n"
            rendered += "\n"
        elif item is linebreak:
            if not rendered.endswith("\n"):
                rendered += "\n"
        else:
            if getattr(item, "inline", False):
                if rendered and not rendered.endswith((" ", "\n")):
                    rendered += " "
                elif not rendered:
                    rendered += " "
                rendered += item.rebuild(indent=0)
                if inline_comment_newline:
                    rendered += "\n"
            else:
                if rendered and not rendered.endswith("\n"):
                    rendered += "\n"
                rendered += item.rebuild(indent=indent) + "\n"
    return rendered


def format_interstitial_trivia_with_separator(
    items: list[Any],
    layout: Layout,
    *,
    indent: int,
    inline_comment_newline: bool = False,
    inline_sep: str = " ",
    include_indent: bool = True,
    drop_blank_line_if_items: bool = True,
    strip_leading_newline_after: str | None = None,
) -> tuple[str, str]:
    """Render interstitial trivia and its separator in one step."""
    if drop_blank_line_if_items and items:
        layout = layout.model_copy(update={"blank_line": False})
    rendered = format_interstitial_trivia(
        items,
        indent=indent,
        inline_comment_newline=inline_comment_newline,
    )
    if (
        strip_leading_newline_after
        and strip_leading_newline_after.endswith("\n")
        and rendered.startswith("\n")
    ):
        rendered = rendered[1:]
    separator = separator_from_layout_with_comments(
        layout,
        rendered,
        inline_sep=inline_sep,
        include_indent=include_indent,
    )
    return rendered, separator


def format_inline_comment_suffix(items: list[Any]) -> str:
    """Join inline comments with a leading separating space."""
    if not items:
        return ""
    suffix = ""
    for item in items:
        if not suffix.endswith(" "):
            suffix += " "
        suffix += item.rebuild(indent=0)
    return suffix


def trim_trailing_layout_newline(trivia_list: list[Any], rendered: str) -> str:
    """Drop a trailing newline when the trivia list doesn't demand one."""
    if (
        trivia_list
        and trivia_list[-1] not in (linebreak, empty_line)
        and rendered.endswith("\n")
    ):
        return rendered[:-1]
    return rendered


def _select_comment_nodes_between(
    comments: Iterable[Node], start: Node, end: Node
) -> list[Node]:
    """Filter comment nodes between *start* and *end* inclusively."""
    selected = [
        comment
        for comment in comments
        if start.end_byte <= comment.start_byte < end.start_byte
    ]
    selected.sort(key=lambda comment: comment.start_byte)
    return selected


def _collect_comment_trivia(
    parent: Node,
    selected: Iterable[Node],
    *,
    start: Node,
    end: Node | None,
    allow_inline: bool,
    include_linebreak: bool,
    inline_requires_gap: bool,
    include_empty_line: bool,
) -> list[Any]:
    """Build comment trivia items while honoring inline/blank-line rules."""
    from nix_manipulator.expressions.comment import Comment

    selected = list(selected)
    prev = start
    collected: list[Any] = []
    for comment_node in selected:
        append_gap_between_offsets(
            collected,
            parent,
            prev,
            comment_node,
            include_linebreak=include_linebreak,
        )
        comment_expr = Comment.from_cst(comment_node)
        if allow_inline and comment_node.start_point.row == prev.end_point.row:
            if not inline_requires_gap or comment_node.start_byte > prev.end_byte:
                comment_expr.inline = True
        collected.append(comment_expr)
        prev = comment_node
    if (
        include_empty_line
        and end is not None
        and selected
        and gap_has_empty_line_from_offsets(parent, prev.end_byte, end.start_byte)
    ):
        collected.append(empty_line)
    return collected


def _collect_comment_trivia_between(
    parent: Node,
    comments: Iterable[Node],
    start: Node,
    end: Node,
    *,
    allow_inline: bool,
    include_linebreak: bool,
    inline_requires_gap: bool,
    include_empty_line: bool,
) -> tuple[list[Any], list[Node]]:
    """Collect between-node trivia and return the selected comment nodes."""
    selected = _select_comment_nodes_between(comments, start, end)
    collected = _collect_comment_trivia(
        parent,
        selected,
        start=start,
        end=end,
        allow_inline=allow_inline,
        include_linebreak=include_linebreak,
        inline_requires_gap=inline_requires_gap,
        include_empty_line=include_empty_line,
    )
    return collected, selected


def append_comment_between(
    trivia: list[Any],
    parent: Node,
    prev: Node | None,
    comment_node: Node,
):
    """Append gap trivia and a comment node to a trivia list."""
    from nix_manipulator.expressions.comment import Comment

    if prev is not None:
        append_gap_between_offsets(trivia, parent, prev, comment_node)
    comment_expr = Comment.from_cst(comment_node)
    trivia.append(comment_expr)
    return comment_expr


def split_inline_comments(items: list[Any]) -> tuple[list[Any], list[Any]]:
    """Split inline comments from other trivia items."""
    from nix_manipulator.expressions.comment import Comment

    inline_comments: list[Any] = []
    remaining: list[Any] = []
    for item in items:
        if isinstance(item, Comment) and item.inline:
            inline_comments.append(item)
        else:
            remaining.append(item)
    return remaining, inline_comments


def collect_comment_trivia_between(
    parent: Node,
    comments: Iterable[Node],
    start: Node,
    end: Node,
    *,
    allow_inline: bool = False,
    include_linebreak: bool = True,
    inline_requires_gap: bool = False,
) -> list[Any]:
    """Collect comment trivia between nodes with configurable whitespace rules."""
    collected, _ = _collect_comment_trivia_between(
        parent,
        comments,
        start=start,
        end=end,
        allow_inline=allow_inline,
        include_linebreak=include_linebreak,
        inline_requires_gap=inline_requires_gap,
        include_empty_line=True,
    )
    return collected


def collect_trailing_comment_trivia(
    parent: Node,
    comments: Iterable[Node],
    start: Node,
    *,
    allow_inline: bool = False,
    include_linebreak: bool = True,
    inline_requires_gap: bool = False,
) -> list[Any]:
    """Collect comment trivia after a node without trailing-gap tracking."""
    selected = [
        comment for comment in comments if comment.start_byte > start.end_byte
    ]
    selected.sort(key=lambda comment: comment.start_byte)
    return _collect_comment_trivia(
        parent,
        selected,
        start=start,
        end=None,
        allow_inline=allow_inline,
        include_linebreak=include_linebreak,
        inline_requires_gap=inline_requires_gap,
        include_empty_line=False,
    )


def collect_comments_between_with_gap(
    parent: Node,
    comments: Iterable[Node],
    start: Node,
    end: Node,
    *,
    allow_inline: bool = False,
) -> tuple[list[Any], str]:
    """Collect comments between nodes and return trailing gap text."""
    collected, selected = _collect_comment_trivia_between(
        parent,
        comments,
        start=start,
        end=end,
        allow_inline=allow_inline,
        include_linebreak=True,
        inline_requires_gap=False,
        include_empty_line=True,
    )
    last = selected[-1] if selected else start
    gap = gap_between(parent, last, end)
    return collected, gap


def parse_delimited_sequence(
    parent: Node,
    content_nodes: list[Node],
    *,
    parse_item: Callable[[Node, list[Any]], Any | None],
    can_inline_comment: Callable[[Node | None, Node, list[Any]], bool],
    attach_inline_comment: Callable[[Any, Any], None],
    open_token: str | None = None,
    close_token: str | None = None,
    initial_trivia: list[Any] | None = None,
) -> tuple[list[Any], list[Any]]:
    """Parse a delimited sequence with consistent trivia handling."""
    from nix_manipulator.expressions.comment import Comment

    items: list[Any] = []
    before: list[Any] = list(initial_trivia) if initial_trivia else []
    inner_trivia: list[Any] = []

    def push_gap(prev: Node | None, cur: Node) -> None:
        """Capture spacing between sequence items for later trivia attachment."""
        if prev is None:
            return
        append_gap_between_offsets(before, parent, prev, cur)

    if content_nodes and open_token is not None:
        opening = next(
            (child for child in parent.children if child.type == open_token), None
        )
        if opening is not None:
            if gap_has_empty_line_from_offsets(
                parent, opening.end_byte, content_nodes[0].start_byte
            ):
                before.append(empty_line)

    prev_content: Node | None = None
    for child in content_nodes:
        if child.type == "comment":
            if can_inline_comment(prev_content, child, items):
                push_gap(prev_content, child)
                comment_expr = Comment.from_cst(child)
                comment_expr.inline = True
                attach_inline_comment(items[-1], comment_expr)
            else:
                append_comment_between(before, parent, prev_content, child)
            prev_content = child
            continue

        push_gap(prev_content, child)
        item = parse_item(child, before)
        if item is not None:
            items.append(item)
            before = []
        prev_content = child

    if before:
        if items:
            items[-1].after.extend(before)
        else:
            inner_trivia = before

    if content_nodes and close_token is not None:
        closing = next(
            (child for child in parent.children if child.type == close_token), None
        )
        if closing is not None:
            if gap_has_empty_line_from_offsets(
                parent, content_nodes[-1].end_byte, closing.start_byte
            ):
                if items:
                    items[-1].after.append(empty_line)
                else:
                    inner_trivia.append(empty_line)

    return items, inner_trivia


def gap_from_offsets(parent: Node, start_byte: int, end_byte: int) -> str:
    """Return source text between absolute byte offsets in *parent*."""
    if start_byte == end_byte:
        return ""
    span = _gap_span(parent, start_byte, end_byte)
    if span is None:
        return ""
    source_bytes, start, end = span
    return source_bytes[start:end].decode()


def gap_between(parent: Node, start: Node, end: Node) -> str:
    """Return the source text between two nodes from their shared parent."""
    return gap_from_offsets(parent, start.end_byte, end.start_byte)

def gap_line_info(
    parent: Node, start: Node, end: Node
) -> tuple[int, int | None]:
    """Return newline count and trailing indent for the gap between nodes."""
    return _gap_line_info_from_offsets(parent, start.end_byte, end.start_byte)


def gap_has_empty_line(gap: str) -> bool:
    """True when a whitespace gap contains a blank line."""
    if "\n" not in gap:
        return False
    if gap.count("\n") < 2:
        return False
    return _EMPTY_LINE_RE.search(gap) is not None


def gap_has_empty_line_from_offsets(
    parent: Node, start_byte: int, end_byte: int
) -> bool:
    """True when whitespace between offsets contains a blank line."""
    span = _gap_span(parent, start_byte, end_byte)
    if span is None:
        return False
    source_bytes, start, end = span
    return _gap_has_empty_line_offsets(source_bytes, start, end)


def gap_has_newline_from_offsets(
    parent: Node, start_byte: int, end_byte: int
) -> bool:
    """True when whitespace between offsets contains a newline."""
    span = _gap_span(parent, start_byte, end_byte)
    if span is None:
        return False
    source_bytes, start, end = span
    return source_bytes.find(b"\n", start, end) != -1


def append_gap_trivia(
    trivia: list[Any], gap: str, *, include_linebreak: bool = True
) -> None:
    """Append empty_line/linebreak markers based on a whitespace gap."""
    if gap_has_empty_line(gap):
        trivia.append(empty_line)
    elif include_linebreak and "\n" in gap:
        trivia.append(linebreak)


def append_gap_trivia_from_offsets(
    trivia: list[Any],
    parent: Node,
    start_byte: int,
    end_byte: int,
    *,
    include_linebreak: bool = True,
) -> None:
    """Append empty_line/linebreak markers for whitespace between offsets."""
    span = _gap_span(parent, start_byte, end_byte)
    if span is None:
        return
    source_bytes, start, end = span
    first_newline = source_bytes.find(b"\n", start, end)
    if first_newline == -1:
        return
    if _gap_has_empty_line_offsets(source_bytes, start, end, first_newline):
        trivia.append(empty_line)
    elif include_linebreak:
        trivia.append(linebreak)


def trim_leading_layout_trivia(trivia: list[Any]) -> list[Any]:
    """Drop leading layout-only trivia markers (linebreak/empty_line)."""
    trimmed = list(trivia)
    while trimmed and trimmed[0] in (linebreak, empty_line):
        trimmed.pop(0)
    return trimmed


def append_gap_between(
    trivia: list[Any],
    parent: Node,
    start: Node,
    end: Node,
    *,
    include_linebreak: bool = True,
) -> str:
    """Append trivia for the whitespace between nodes and return the gap."""
    gap = gap_between(parent, start, end)
    append_gap_trivia(trivia, gap, include_linebreak=include_linebreak)
    return gap


def append_gap_between_offsets(
    trivia: list[Any],
    parent: Node,
    start: Node,
    end: Node,
    *,
    include_linebreak: bool = True,
) -> None:
    """Append trivia for the whitespace between nodes (offsets only)."""
    append_gap_trivia_from_offsets(
        trivia,
        parent,
        start.end_byte,
        end.start_byte,
        include_linebreak=include_linebreak,
    )


def indent_from_gap(gap: str) -> int:
    """Indentation after the last newline in *gap*, or 0 if there is none."""
    if "\n" not in gap:
        return 0
    return len(gap.rsplit("\n", 1)[-1])


def apply_trailing_trivia(rebuilt: str, after: list[Any], *, indent: int) -> str:
    """
    Append trailing trivia to a preformatted string.

    This mirrors NixExpression.add_trivia's inline-comment handling, but it
    assumes *rebuilt* already includes any leading trivia/indentation.
    """
    from nix_manipulator.expressions.comment import Comment

    if not after:
        return rebuilt
    if isinstance(after[0], Comment) and after[0].inline:
        inline_comment = after[0].rebuild(indent=0)
        trailing = format_trivia(after[1:], indent=indent)
        trailing = trim_trailing_layout_newline(after, trailing)
        return f"{rebuilt} {inline_comment}" + (f"\n{trailing}" if trailing else "")

    after_str = format_trivia(after, indent=indent)
    after_str = trim_trailing_layout_newline(after, after_str)
    return rebuilt + (f"\n{after_str}" if after_str else "")
