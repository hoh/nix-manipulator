"""Cover remaining expression branches for coverage."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nix_manipulator import mapping, parser
from nix_manipulator.cli.manipulations import _resolve_target_set_from_expr
from nix_manipulator.expressions import select as select_module
from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binary import BinaryExpression
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.if_expression import IfExpression
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.select import Select
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.source_code import NixSourceCode
from nix_manipulator.expressions.trivia import (_gap_has_empty_line_offsets,
                                                format_interstitial_trivia,
                                                gap_from_offsets)
from nix_manipulator.expressions.with_statement import WithStatement


@dataclass
class DummyPoint:
    row: int = 0
    column: int = 0


@dataclass
class StubNode:
    type: str
    text: bytes | None = None
    children: list["StubNode"] = field(default_factory=list)
    field_map: dict[str, "StubNode"] = field(default_factory=dict)
    start_byte: int = 0
    end_byte: int = 0
    start_point: DummyPoint = field(default_factory=DummyPoint)
    end_point: DummyPoint = field(default_factory=DummyPoint)

    def child_by_field_name(self, name: str) -> "StubNode" | None:
        return self.field_map.get(name)


@dataclass(slots=True)
class DummyExpr(NixExpression):
    text: str = ""

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        return self.text


def parse_expr(source: str):
    """Parse and return the first top-level expression."""
    parsed = parser.parse(source)
    assert parsed.expressions
    return parsed.expressions[0]


def test_if_expression_comment_routing():
    """Non-inline comments between then/else and branches should stick."""
    expr = parse_expr("if true then\n  # then\n  1 else\n  # else\n  2")
    assert isinstance(expr, IfExpression)
    assert expr.consequence.before
    assert expr.alternative.before


def test_list_inline_comment_and_empty_gap():
    """Inline list comments and empty-line gaps should be preserved."""
    expr = parse_expr("[ 1 # inline\n]")
    assert isinstance(expr, NixList)
    assert expr.value[0].after

    expr = parse_expr("[\n\n]")
    assert isinstance(expr, NixList)
    assert expr.inner_trivia


def test_list_auto_multiline_and_scoped():
    """Force multiline inference and scoped rebuilds."""
    item = Primitive(value=1)
    item.before = [Comment(text="note")]
    nix_list = NixList(value=[item], multiline=None)
    assert nix_list._auto_multiline(indent=0, inline=False)

    nix_list = NixList(value=[Primitive(value=1)], inner_trivia=[empty_line])
    assert nix_list._auto_multiline(indent=0, inline=False)
    assert nix_list.simple_inline_preview(indent=0) is None

    long_item = Primitive(value="x" * 200)
    nix_list = NixList(value=[long_item], multiline=False)
    assert nix_list.simple_inline_preview(indent=0, max_width=1) is None

    nix_list.scope.append(Binding(name="scoped", value=Primitive(value=0)))
    assert "let" in nix_list.rebuild()


def test_parenthesis_inline_and_leading_comments(monkeypatch):
    """Exercise comment attachment inside parenthesis parsing."""
    monkeypatch.setattr(mapping, "tree_sitter_node_to_expression", lambda node: Primitive(value=1))

    open_paren = StubNode(
        type="(",
        start_byte=0,
        end_byte=1,
        start_point=DummyPoint(row=0, column=0),
        end_point=DummyPoint(row=0, column=1),
    )
    value = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=1,
        end_byte=2,
        start_point=DummyPoint(row=0, column=1),
        end_point=DummyPoint(row=0, column=2),
    )
    inline_comment = StubNode(
        type="comment",
        text=b"# c",
        start_byte=2,
        end_byte=4,
        start_point=DummyPoint(row=0, column=2),
        end_point=DummyPoint(row=0, column=4),
    )
    close_paren = StubNode(
        type=")",
        start_byte=4,
        end_byte=5,
        start_point=DummyPoint(row=0, column=4),
        end_point=DummyPoint(row=0, column=5),
    )
    node = StubNode(
        type="parenthesized_expression",
        text=b"(1#c)",
        children=[open_paren, value, inline_comment, close_paren],
    )
    expr = Parenthesis.from_cst(node)
    assert expr.value.after

    open_paren = StubNode(
        type="(",
        start_byte=0,
        end_byte=1,
        start_point=DummyPoint(row=0, column=0),
        end_point=DummyPoint(row=0, column=1),
    )
    lead_comment = StubNode(
        type="comment",
        text=b"# lead",
        start_byte=1,
        end_byte=7,
        start_point=DummyPoint(row=0, column=1),
        end_point=DummyPoint(row=0, column=6),
    )
    value = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=8,
        end_byte=9,
        start_point=DummyPoint(row=1, column=0),
        end_point=DummyPoint(row=1, column=1),
    )
    close_paren = StubNode(
        type=")",
        start_byte=9,
        end_byte=10,
        start_point=DummyPoint(row=1, column=1),
        end_point=DummyPoint(row=1, column=2),
    )
    node = StubNode(
        type="parenthesized_expression",
        text=b"(# lead\n1)",
        children=[open_paren, lead_comment, value, close_paren],
    )
    expr = Parenthesis.from_cst(node)
    assert expr.value.before

    open_paren = StubNode(
        type="(",
        start_byte=0,
        end_byte=1,
        start_point=DummyPoint(row=0, column=0),
        end_point=DummyPoint(row=0, column=1),
    )
    value = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=1,
        end_byte=2,
        start_point=DummyPoint(row=0, column=1),
        end_point=DummyPoint(row=0, column=2),
    )
    second = StubNode(
        type="integer_expression",
        text=b"2",
        start_byte=2,
        end_byte=3,
        start_point=DummyPoint(row=0, column=2),
        end_point=DummyPoint(row=0, column=3),
    )
    close_paren = StubNode(
        type=")",
        start_byte=3,
        end_byte=4,
        start_point=DummyPoint(row=0, column=3),
        end_point=DummyPoint(row=0, column=4),
    )
    node = StubNode(
        type="parenthesized_expression",
        text=b"(12)",
        children=[open_paren, value, second, close_paren],
    )
    with pytest.raises(ValueError, match="Parenthesis contains multiple expressions"):
        Parenthesis.from_cst(node)


def test_parenthesis_rebuild_branches():
    """Cover multiline rebuild and scoped handling."""
    expr = Parenthesis(
        value=Primitive(value=1),
        leading_gap="",
        trailing_gap="\n",
    )
    assert "\n" in expr.rebuild()

    expr.scope.append(Binding(name="scoped", value=Primitive(value=0)))
    assert "let" in expr.rebuild()


def test_select_layout_and_scope():
    """Exercise select layout handling and scoped rebuilds."""
    expr = Select(
        expression=DummyExpr(text="value\n"),
        attribute="attr",
        attr_gap="\n\n  ",
    )
    rebuilt = expr.rebuild()
    assert ".attr" in rebuilt

    expr.scope.append(Binding(name="scoped", value=Primitive(value=0)))
    assert "let" in expr.rebuild()


def test_select_default_comment_newline(monkeypatch):
    """Append newline after default comments when missing."""
    monkeypatch.setattr(
        select_module, "format_trivia", lambda *_args, **_kwargs: "# note"
    )
    expr = Select(
        expression=Primitive(value="x"),
        attribute="attr",
        default=Primitive(value=1),
        default_gap="\n",
        default_before=[Comment(text="note")],
    )
    rebuilt = expr.rebuild()
    assert "# note\n" in rebuilt
    assert "or" in rebuilt


def test_attribute_set_empty_line_and_trailing_newline():
    """Cover empty-line inner trivia and newline-ending bindings."""
    expr = parse_expr("{\n\n}")
    assert isinstance(expr, AttributeSet)
    assert expr.inner_trivia

    binding = BinaryExpression(operator="+", left=Primitive(value=1), right=Primitive(value=2))
    attr_binding = AttributeSet.from_dict({"a": binding}).values[0]
    attr_binding.after = [Comment(text="note"), linebreak]
    attrset = AttributeSet(values=[attr_binding], multiline=True)
    assert attrset.rebuild().endswith("}")


def test_source_code_leading_trivia():
    """Leading whitespace should be attached to the first expression."""
    parsed = parser.parse("# lead\n1")
    assert isinstance(parsed, NixSourceCode)
    assert parsed.expressions[0].before


def test_trivia_gap_and_interstitial_formatting():
    """Exercise gap/formatting helpers for edge branches."""
    assert not _gap_has_empty_line_offsets(b"1\n2\n3", 0, 5)

    inline_one = Comment(text="one", inline=True)
    inline_two = Comment(text="two", inline=True)
    rendered = format_interstitial_trivia([inline_one, inline_two], indent=0)
    assert "# one" in rendered

    rendered = format_interstitial_trivia([inline_one, Comment(text="block")], indent=0)
    assert "\n# block" in rendered

    parent = StubNode(type="root", text=None)
    assert gap_from_offsets(parent, 0, 1) == ""


def test_with_statement_comment_routing_and_rebuild():
    """Cover comment routing and layout branches in with statements."""
    expr = parse_expr("with foo;\n# comment\nbar")
    assert isinstance(expr, WithStatement)
    assert expr.body.before

    env = Primitive(value="env")
    env.before = [linebreak]
    body = Primitive(value=1, before=[empty_line])
    stmt = WithStatement(
        environment=env,
        body=body,
        after_with_gap="\n",
    )
    rebuilt = stmt.rebuild(indent=2)
    assert "\n" in rebuilt

    stmt = WithStatement(
        environment=Primitive(value="env"),
        body=Primitive(value=1, before=[empty_line]),
    )
    assert "\n\n" in stmt.rebuild(indent=2)


def test_manipulations_target_resolution():
    """Resolve target sets from assertion and function definitions."""
    attrset = AttributeSet.from_dict({"a": Primitive(value=1)})
    assertion = Assertion(expression=Primitive(value=True), body=attrset)
    assert _resolve_target_set_from_expr(assertion) is attrset

    func = FunctionDefinition(argument_set=Identifier(name="a"), output=attrset)
    assert _resolve_target_set_from_expr(func) is attrset
