"""Target low-level trivia helpers to reach coverage thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.layout import comma, empty_line, linebreak
from nix_manipulator.expressions.trivia import (
    Layout,
    _collect_comment_trivia,
    _gap_has_empty_line_offsets,
    _gap_line_info_from_offsets,
    _gap_span,
    append_gap_between,
    append_gap_trivia,
    format_interstitial_trivia,
    format_interstitial_trivia_with_separator,
    format_trivia,
    gap_from_offsets,
    indent_from_gap,
    parse_delimited_sequence,
    separator_from_layout,
    separator_from_layout_with_comments,
)


@dataclass
class DummyPoint:
    row: int = 0
    column: int = 0


@dataclass
class DummyNode:
    type: str
    text: bytes | None = None
    start_byte: int = 0
    end_byte: int = 0
    start_point: DummyPoint = field(default_factory=DummyPoint)
    end_point: DummyPoint = field(default_factory=DummyPoint)
    children: list["DummyNode"] = field(default_factory=list)


@dataclass
class DummyItem:
    text: str
    before: list = field(default_factory=list)
    after: list = field(default_factory=list)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        return self.text


def test_gap_span_and_line_info_edges():
    """Cover gap helpers for missing text and invalid offsets."""
    assert _gap_span(DummyNode(type="root", text=None), 0, 1) is None
    assert _gap_span(DummyNode(type="root", text=b"abc", start_byte=5), 1, 2) is None
    assert _gap_line_info_from_offsets(DummyNode(type="root", text=None), 0, 1) == (
        0,
        None,
    )


def test_gap_empty_line_offsets():
    """Exercise empty-line detection over byte spans."""
    blob = b"line\n \nnext"
    assert _gap_has_empty_line_offsets(blob, 0, len(blob)) is True


def test_layout_and_separator_helpers():
    """Cover layout helpers and separator formatting."""
    layout = Layout(on_newline=True, blank_line=True, indent=2)
    assert layout.model_copy() == layout
    assert layout.with_indent(4).indent == 4
    assert indent_from_gap(" ") == 0
    assert separator_from_layout(layout, indent=0) == "\n\n  "
    assert "\n\n" in separator_from_layout_with_comments(layout, "comment")


def test_format_trivia_variants():
    """Cover comma handling and error cases in trivia formatting."""
    inline_comment = Comment(text="inline", inline=True)
    assert "," in format_trivia([comma, inline_comment], indent=2)
    assert "\n" in format_trivia([comma, linebreak], indent=0)

    with pytest.raises(NotImplementedError):
        format_trivia([object()])


def test_format_interstitial_trivia_branches():
    """Exercise interstitial trivia with empty lines and inline comments."""
    inline = Comment(text="c", inline=True)
    block = Comment(text="b", inline=False)
    rendered = format_interstitial_trivia(
        [empty_line, inline, block], indent=2, inline_comment_newline=True
    )
    assert "\n" in rendered
    assert "c" in rendered

    layout = Layout(on_newline=True, blank_line=True, indent=2)
    rendered, _ = format_interstitial_trivia_with_separator(
        [linebreak],
        layout,
        indent=0,
        strip_leading_newline_after="\n",
    )
    assert not rendered.startswith("\n")


def test_collect_comment_trivia_appends_empty_line():
    """Ensure empty lines are appended when gaps contain blank lines."""
    parent = DummyNode(type="root", text=b"a\n\n# c\n\nb")
    start = DummyNode(type="start", text=b"a", start_byte=0, end_byte=1)
    end = DummyNode(type="end", text=b"b", start_byte=8, end_byte=9)
    comment_node = DummyNode(
        type="comment",
        text=b"# c",
        start_byte=3,
        end_byte=6,
        start_point=DummyPoint(row=1, column=0),
        end_point=DummyPoint(row=1, column=3),
    )
    collected = _collect_comment_trivia(
        parent,
        [comment_node],
        start=start,
        end=end,
        allow_inline=True,
        include_linebreak=True,
        inline_requires_gap=True,
        include_empty_line=True,
    )
    assert empty_line in collected


def test_parse_delimited_sequence_trivia_paths():
    """Cover empty-line handling at open/close and inner trivia fallback."""
    parent = DummyNode(
        type="list",
        text=b"[\n\nx\n\n]",
        children=[],
    )
    opening = DummyNode(type="[", start_byte=0, end_byte=1)
    item = DummyNode(type="identifier", text=b"x", start_byte=3, end_byte=4)
    closing = DummyNode(type="]", start_byte=6, end_byte=7)
    parent.children = [opening, item, closing]

    def parse_item(_node: DummyNode, before: list):
        expr = DummyItem(text="x")
        expr.before = before
        return expr

    def can_inline_comment(_prev, _comment, _items):
        return False

    def attach_inline_comment(_item, _comment):
        raise AssertionError("no inline comments expected")

    items, inner_trivia = parse_delimited_sequence(
        parent,
        [item],
        parse_item=parse_item,
        can_inline_comment=can_inline_comment,
        attach_inline_comment=attach_inline_comment,
        open_token="[",
        close_token="]",
        initial_trivia=[empty_line],
    )
    assert items
    assert empty_line in inner_trivia or empty_line in items[0].before


def test_parse_delimited_sequence_inner_trivia_for_empty_items():
    """Capture inner trivia when only comments appear between delimiters."""
    parent = DummyNode(type="list", text=b"[# c\n\n]")
    opening = DummyNode(type="[", start_byte=0, end_byte=1)
    comment = DummyNode(
        type="comment",
        text=b"# c",
        start_byte=1,
        end_byte=4,
        start_point=DummyPoint(row=0, column=1),
        end_point=DummyPoint(row=0, column=4),
    )
    closing = DummyNode(type="]", start_byte=6, end_byte=7)
    parent.children = [opening, comment, closing]

    def parse_item(_node: DummyNode, _before: list):
        return None

    def can_inline_comment(_prev, _comment, _items):
        return False

    def attach_inline_comment(_item, _comment):
        raise AssertionError("no inline comments expected")

    items, inner_trivia = parse_delimited_sequence(
        parent,
        [comment],
        parse_item=parse_item,
        can_inline_comment=can_inline_comment,
        attach_inline_comment=attach_inline_comment,
        open_token="[",
        close_token="]",
        initial_trivia=[empty_line],
    )
    assert not items
    assert inner_trivia


def test_gap_helpers_and_trivia_appenders():
    """Cover gap helpers and trailing trivia appenders."""
    parent = DummyNode(type="root", text=None)
    assert gap_from_offsets(parent, 0, 0) == ""

    trivia: list = []
    append_gap_trivia(trivia, "\n\n")
    append_gap_trivia(trivia, "\n")
    assert empty_line in trivia
    assert linebreak in trivia

    parent = DummyNode(type="root", text=b"a\nb")
    start = DummyNode(type="start", start_byte=0, end_byte=1)
    end = DummyNode(type="end", start_byte=2, end_byte=3)
    gap = append_gap_between(trivia, parent, start, end)
    assert "\n" in gap
