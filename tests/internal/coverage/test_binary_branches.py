"""Target binary-expression branches that are hard to hit via fixtures."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nix_manipulator import mapping, parser
from nix_manipulator.expressions import binary as binary_module
from nix_manipulator.expressions.binary import (BinaryExpression,
                                                _clone_with_trivia,
                                                _ensure_indent,
                                                _format_chained_binary,
                                                _rebuild_operand)
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.operator import Operator
from nix_manipulator.expressions.primitive import Primitive


def parse_expr(source: str):
    """Parse and return the first top-level expression."""
    parsed = parser.parse(source)
    assert parsed.expressions
    return parsed.expressions[0]


def test_clone_with_trivia_and_rebuild_operand():
    """Cover trivia merges and inline rebuild behavior."""
    expr = Primitive(value=1)
    expr.before = [Comment(text="lead")]
    extra_before = [Comment(text="extra")]
    extra_after = [Comment(text="tail")]

    cloned = _clone_with_trivia(expr, extra_before, extra_after)
    assert cloned is not expr
    assert cloned.before[0].text == "extra"
    assert cloned.after[-1].text == "tail"

    expected = expr.rebuild(indent=2, inline=False)
    assert _rebuild_operand(expr, indent=2, inline=True) == expected


def test_ensure_indent_variants():
    """Exercise indent guarding for empty, blank, and under-indented text."""
    assert _ensure_indent("", 2) == ""
    assert _ensure_indent("\nvalue", 2) == "\nvalue"
    assert _ensure_indent("x", 2) == "  x"


def test_binary_post_init_conversions_and_errors():
    """Coerce primitives and error on unsupported operator types."""
    expr = BinaryExpression(operator="++", left=1, right=2)
    assert isinstance(expr.left, Primitive)
    assert isinstance(expr.right, Primitive)
    assert isinstance(expr.operator, Operator)

    with pytest.raises(ValueError, match="Unsupported operator type"):
        BinaryExpression(operator=object(), left=1, right=2)


def test_binary_chained_rebuild_branches():
    """Hit chained formatting branches for newline and inline operators."""
    inner = BinaryExpression(
        operator="++",
        left=Primitive(value=1),
        right=Primitive(value=2),
        operator_gap_lines=1,
        right_gap_lines=1,
        before=[Comment(text="lead")],
        after=[Comment(text="trail")],
    )
    outer = BinaryExpression(
        operator="++",
        left=inner,
        right=Primitive(value=3),
        operator_gap_lines=1,
        right_gap_lines=0,
    )
    chained = _format_chained_binary(outer, indent=0, inline=False)
    assert chained is not None
    assert "\n" in chained

    inner_inline = BinaryExpression(
        operator="++",
        left=Primitive(value=1),
        right=Primitive(value=2),
        operator_gap_lines=0,
        right_gap_lines=0,
    )
    outer_inline = BinaryExpression(
        operator="++",
        left=inner_inline,
        right=Primitive(value=3),
        operator_gap_lines=1,
        right_gap_lines=0,
    )
    chained_inline = _format_chained_binary(outer_inline, indent=0, inline=False)
    assert chained_inline is not None


def test_binary_rebuild_gap_branches():
    """Cover operator/right gap handling in rebuild."""
    expr_newline = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=Primitive(value=2),
        operator_gap_lines=1,
        right_gap_lines=1,
    )
    assert "\n" in expr_newline.rebuild()

    right_chain = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=BinaryExpression(
            operator="+",
            left=Primitive(value=2),
            right=Primitive(value=3),
            operator_gap_lines=1,
        ),
        right_gap_lines=1,
    )
    assert "\n" in right_chain.rebuild()

    expr_inline = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=Primitive(value=2),
    )
    assert " + " in expr_inline.rebuild()


def test_binary_format_chained_single_operand():
    """Return None when chaining has only one operand."""
    stub = SimpleNamespace(operator=Operator(name="++"), operator_gap_lines=1)
    assert _format_chained_binary(stub, indent=0, inline=False) is None


def test_binary_from_cst_comment_routing():
    """Parse comments around operators to exercise comment routing logic."""
    source = "1 # left\n+ # op\n2#edge\n"
    expr = parse_expr(source)
    assert isinstance(expr, BinaryExpression)
    assert expr.left.after


def test_binary_from_cst_clamps_right_gap_lines(monkeypatch):
    """Clamp right-gap line counts when comments are present."""
    monkeypatch.setattr(
        mapping, "tree_sitter_node_to_expression", lambda node: Primitive(value=1)
    )
    monkeypatch.setattr(
        binary_module,
        "_collect_binary_comment_trivia",
        lambda *args: ([], [Comment(text="c")], [], []),
    )
    calls = iter([(0, None), (2, None)])
    monkeypatch.setattr(binary_module, "gap_line_info", lambda *_args: next(calls))

    point = SimpleNamespace(row=0, column=0)
    left = SimpleNamespace(
        type="integer_expression",
        text=b"1",
        start_byte=0,
        end_byte=1,
        start_point=point,
        end_point=point,
    )
    operator = SimpleNamespace(
        type="operator",
        text=b"+",
        start_byte=2,
        end_byte=3,
        start_point=point,
        end_point=point,
    )
    right = SimpleNamespace(
        type="integer_expression",
        text=b"2",
        start_byte=4,
        end_byte=5,
        start_point=point,
        end_point=point,
    )
    node = SimpleNamespace(
        type="binary_expression",
        text=b"1 + 2",
        children=[left, operator, right],
        start_byte=0,
        end_byte=5,
        start_point=point,
        end_point=point,
    )
    expr = BinaryExpression.from_cst(node)
    assert expr.right_gap_lines == 1


def test_binary_absorbable_helpers():
    """Cover absorbable term helpers and chainable absorption branch."""
    from nix_manipulator.expressions.indented_string import IndentedString
    from nix_manipulator.expressions.list import NixList
    from nix_manipulator.expressions.parenthesis import Parenthesis
    from nix_manipulator.expressions.set import AttributeSet

    list_expr = NixList(value=[Primitive(value=1), Primitive(value=2)])
    assert binary_module._is_absorbable_term(list_expr) is False
    assert binary_module._is_absorbable_term(
        NixList(value=[Primitive(value=1)])
    ) is True

    parenthesized = Parenthesis(value=list_expr)
    assert binary_module._is_absorbable_term(parenthesized) is False

    assert binary_module._is_absorbable_term(AttributeSet(values=[])) is True
    assert binary_module._is_absorbable_term(IndentedString(value="\n  ok\n")) is True

    with_comment = IndentedString(value="\n  ok\n")
    with_comment.before = [Comment(text="note")]
    assert binary_module._has_leading_comment(with_comment) is True
    assert binary_module._should_absorb_chainable_operand(with_comment) is False

    no_comment = IndentedString(value="\n  ok\n")
    assert binary_module._has_leading_comment(no_comment) is False
    assert binary_module._should_absorb_chainable_operand(no_comment) is True

    expr = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=IndentedString(value="\n  ok\n"),
        operator_gap_lines=1,
        right_gap_lines=1,
    )
    assert "\n" in expr.rebuild()


def test_binary_from_cst_comment_routing_stub(monkeypatch):
    """Route comments to right-side trivia branches via stubs."""
    monkeypatch.setattr(mapping, "tree_sitter_node_to_expression", lambda node: Primitive(value=1))

    point = SimpleNamespace(row=0, column=0)
    left = SimpleNamespace(type="integer_expression", text=b"1", start_byte=0, end_byte=1)
    operator = SimpleNamespace(type="operator", text=b"+", start_byte=2, end_byte=3)
    right = SimpleNamespace(type="integer_expression", text=b"2", start_byte=6, end_byte=7)
    comment_between = SimpleNamespace(type="comment", text=b"# c", start_byte=4, end_byte=5)
    edge_comment = SimpleNamespace(type="comment", text=b"# e", start_byte=7, end_byte=8)
    trailing_comment = SimpleNamespace(type="comment", text=b"# t", start_byte=9, end_byte=10)
    for node in (left, operator, right, comment_between, edge_comment, trailing_comment):
        node.start_point = point
        node.end_point = point

    node = SimpleNamespace(
        type="binary_expression",
        text=b" " * 20,
        children=[left, operator, comment_between, right, edge_comment, trailing_comment],
        start_byte=0,
        end_byte=10,
        start_point=point,
        end_point=point,
    )
    expr = BinaryExpression.from_cst(node)
    assert expr.right.before or expr.right.after


def test_binary_from_cst_operator_missing(monkeypatch):
    """Cover error when an operator node has no text."""
    monkeypatch.setattr(mapping, "tree_sitter_node_to_expression", lambda node: Primitive(value=1))

    point = SimpleNamespace(row=0, column=0)
    left = SimpleNamespace(type="integer_expression", text=b"1", start_byte=0, end_byte=1)
    operator = SimpleNamespace(type="operator", text=None, start_byte=2, end_byte=3)
    right = SimpleNamespace(type="integer_expression", text=b"2", start_byte=4, end_byte=5)
    for node in (left, operator, right):
        node.start_point = point
        node.end_point = point
    node = SimpleNamespace(
        type="binary_expression",
        text=b"1 + 2",
        children=[left, operator, right],
        start_byte=0,
        end_byte=5,
        start_point=point,
        end_point=point,
    )

    with pytest.raises(ValueError, match="Missing operator"):
        BinaryExpression.from_cst(node)


def test_binary_from_cst_rejects_unknown_type():
    """Reject unsupported node types during parsing."""
    node = SimpleNamespace(type="identifier", text=b"x", children=[])
    with pytest.raises(ValueError, match="Unsupported expression type"):
        BinaryExpression.from_cst(node)


def test_binary_rebuild_right_indent_and_scoped():
    """Cover right-gap newline and scoped rebuild branches."""
    expr = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=Primitive(value=2),
        right_gap_lines=1,
    )
    assert "\n" in expr.rebuild()

    scoped = BinaryExpression(
        operator="+",
        left=Primitive(value=1),
        right=Primitive(value=2),
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()
