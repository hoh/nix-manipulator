"""Exercise function definition and call branches for coverage."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nix_manipulator import mapping, parser
from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.function import definition as func_def
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import (
    FunctionDefinition, _collect_colon_trivia, _parse_argument_set,
    _parse_formal_default, _parse_function_body, _parse_named_argument_set)
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import comma, empty_line, linebreak
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.set import AttributeSet


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


def parse_function_node(source: str):
    """Parse a function definition node from source."""
    root = parser.parse_to_ast(source)
    return next(child for child in root.children if child.type == "function_expression")


def test_parse_named_argument_set_errors():
    """Cover signature validation errors."""
    with pytest.raises(ValueError, match="missing expected tokens"):
        _parse_named_argument_set(StubNode(type="fn", children=[StubNode(type="id")]))

    with pytest.raises(ValueError, match="Unsupported function definition signature"):
        _parse_named_argument_set(
            StubNode(type="fn", children=[StubNode(type="number"), StubNode(type=":")])
        )

    with pytest.raises(ValueError, match="Named argument set is incomplete"):
        _parse_named_argument_set(
            StubNode(
                type="fn",
                children=[StubNode(type="identifier"), StubNode(type="@")],
            )
        )

    with pytest.raises(ValueError, match="Expected formals after named arg set"):
        _parse_named_argument_set(
            StubNode(
                type="fn",
                children=[
                    StubNode(type="identifier", text=b"x"),
                    StubNode(type="@"),
                    StubNode(type="identifier", text=b"y"),
                ],
            )
        )

    with pytest.raises(ValueError, match="Expected formals@identifier syntax"):
        _parse_named_argument_set(
            StubNode(
                type="fn",
                children=[
                    StubNode(type="formals"),
                    StubNode(type="@"),
                    StubNode(type="formals"),
                ],
            )
        )


def test_parse_argument_set_errors_and_edges():
    """Cover error paths in argument parsing."""
    formals = StubNode(type="formals", text=None)
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    with pytest.raises(ValueError, match="Function definition has no formals text"):
        _parse_argument_set(node)

    formals = StubNode(type="formals", text=b"{}", children=[])
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    with pytest.raises(ValueError, match="Function definition formals are empty"):
        _parse_argument_set(node)

    formals = StubNode(
        type="formals",
        text=b"x",
        children=[StubNode(type="identifier")],
    )
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    with pytest.raises(ValueError, match="Function definition formals are missing an opening brace"):
        _parse_argument_set(node)

    formal_child = StubNode(type="formal", children=[StubNode(type="number")])
    formals = StubNode(
        type="formals",
        text=b"{x}",
        children=[StubNode(type="{"), formal_child, StubNode(type="}")],
    )
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    with pytest.raises(ValueError, match="Unsupported child node"):
        _parse_argument_set(node)

    formals = StubNode(
        type="formals",
        text=b"{x}",
        children=[StubNode(type="{"), StubNode(type="oops"), StubNode(type="}")],
    )
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    with pytest.raises(ValueError, match="Unsupported child node"):
        _parse_argument_set(node)

    formals = StubNode(
        type="formals",
        text=b"{,}",
        children=[StubNode(type="{"), StubNode(type="ERROR", text=b","), StubNode(type="}")],
    )
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    parsed = _parse_argument_set(node)
    assert parsed[0] == []

    formals = StubNode(
        type="formals",
        text=b"{,}",
        children=[
            StubNode(type="{"),
            StubNode(type="formal", children=[StubNode(type="identifier", text=b"")]),
            StubNode(type="}"),
        ],
    )
    node = StubNode(type="function_expression", children=[formals], field_map={"formals": formals})
    parsed = _parse_argument_set(node)
    assert parsed[0] == []

    node = StubNode(type="function_expression", children=[StubNode(type="literal")])
    with pytest.raises(ValueError, match="missing its identifier"):
        _parse_argument_set(node)


def test_parse_function_body_errors():
    """Reject missing function bodies."""
    node = StubNode(type="function_expression", children=[])
    with pytest.raises(ValueError, match="Function definition has no body"):
        _parse_function_body(node)


def test_parse_formal_default_with_comments(monkeypatch):
    """Attach inline and block comments while parsing defaults."""
    monkeypatch.setattr(func_def, "gap_between", lambda *_args, **_kwargs: "\n\n")

    parent = StubNode(type="function_expression", text=b"?")
    question = StubNode(
        type="?",
        start_point=DummyPoint(row=0, column=0),
    )
    inline_comment = StubNode(
        type="comment",
        text=b"# inline",
        start_point=DummyPoint(row=0, column=2),
    )
    block_comment = StubNode(
        type="comment",
        text=b"# block",
        start_point=DummyPoint(row=1, column=0),
    )
    value = StubNode(
        type="integer_expression",
        text=b"1",
        start_point=DummyPoint(row=2, column=4),
    )
    identifier = Identifier(name="a")
    _parse_formal_default(parent, iter([inline_comment, block_comment, value]), question, identifier)
    assert identifier.default_value is not None
    assert identifier.after_question
    assert identifier.default_value_on_newline


def test_parse_formal_default_missing_value():
    """Raise a clear error when default values are missing."""
    parent = StubNode(type="function_expression", text=b"?")
    question = StubNode(type="?", start_point=DummyPoint(row=0, column=0))
    comment = StubNode(
        type="comment",
        text=b"# only comment",
        start_point=DummyPoint(row=0, column=2),
    )
    identifier = Identifier(name="a")
    with pytest.raises(ValueError, match="default value is missing"):
        _parse_formal_default(parent, iter([comment]), question, identifier)


def test_function_definition_complex_parse():
    """Parse complex formals to exercise defaults, comments, and ellipses."""
    source = "{ a, b ? 1, ... }: { a = b; }"
    node = parse_function_node(source)
    expr = FunctionDefinition.from_cst(node)
    assert isinstance(expr, FunctionDefinition)
    assert isinstance(expr.argument_set, list)
    assert any(isinstance(arg, Ellipses) for arg in expr.argument_set)


def test_function_definition_pending_commas_and_comments():
    """Trigger pending-comma flush and inline comment attachment."""
    source = """
{ a

, b # inline

}:
  a
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    assert isinstance(expr.argument_set, list)
    assert expr.argument_set_trailing_empty_lines >= 1
    assert any(
        isinstance(arg, Identifier) and arg.after for arg in expr.argument_set
    )

    source = """
{ a
,
  # comment
  b
}:
  a
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    assert isinstance(expr.argument_set, list)

    source = """
{ a

, ...
}:
  a
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    assert any(isinstance(arg, Ellipses) for arg in expr.argument_set)

    source = """
{ a

,
  b
}:
  b
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    assert isinstance(expr.argument_set, list)
    b_arg = next(
        arg for arg in expr.argument_set if isinstance(arg, Identifier) and arg.name == "b"
    )
    assert empty_line in b_arg.before

    source = """
{ a

, # note
  b
}:
  b
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    b_arg = next(
        arg for arg in expr.argument_set if isinstance(arg, Identifier) and arg.name == "b"
    )
    assert any(item is comma for item in b_arg.before)
    assert any(
        isinstance(item, Comment) and item.inline for item in b_arg.before
    )

    source = """
{ a,

  ...
}:
  a
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    ellipses = next(arg for arg in expr.argument_set if isinstance(arg, Ellipses))
    assert empty_line in ellipses.before


def test_collect_colon_trivia_without_colon():
    """Cover colon trivia when the colon node is missing."""
    body = StubNode(type="identifier", text=b"x")
    node = StubNode(type="function_expression", children=[body])
    before, gap, after, breaks, trivia = _collect_colon_trivia(node, body)
    assert before == []
    assert gap == ""
    assert after is None
    assert breaks == 0
    assert trivia == []


def test_function_definition_colon_inline_comment():
    """Attach inline colon comments to the function definition."""
    source = """
{ a }: # after colon
{ a = 1; }
""".strip()
    expr = FunctionDefinition.from_cst(parse_function_node(source))
    assert expr.after_colon_comment is not None


def test_collect_colon_trivia_with_inline_and_between_comments():
    """Exercise colon trivia collection with inline and between comments."""
    source = """
{ a }:
# between
{ a = 1; }
""".strip()
    node = parse_function_node(source)
    body_node = node.child_by_field_name("body")
    assert body_node is not None
    before_colon_comments, before_colon_gap, after_colon_comment, breaks, before_body = _collect_colon_trivia(
        node,
        body_node,
    )
    assert breaks >= 0
    assert before_body
    assert before_colon_gap is not None
    assert before_colon_comments == []
    assert after_colon_comment is None


def test_collect_colon_trivia_with_blank_lines():
    """Preserve blank lines between colon comments and body."""
    source = """
{ a }:
# between

{ a = 1; }
""".strip()
    node = parse_function_node(source)
    body_node = node.child_by_field_name("body")
    assert body_node is not None
    _, _, _, _, before_body = _collect_colon_trivia(node, body_node)
    assert empty_line in before_body


def test_function_definition_render_empty_args_with_comments():
    """Render empty argument sets with inline comments and named args."""
    inner_trivia = [Comment(text="note")]
    func = FunctionDefinition(
        argument_set=[],
        argument_set_inner_trivia=inner_trivia,
        named_attribute_set=Identifier(name="args"),
        named_attribute_set_before_formals=True,
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "args@" in rebuilt
    assert "# note" in rebuilt

    func.named_attribute_set_before_formals = False
    rebuilt = func.rebuild()
    assert "}@args" in rebuilt


def test_function_definition_render_empty_args_with_layout_trivia():
    """Force multiline rendering for empty args with layout trivia."""
    func = FunctionDefinition(
        argument_set=[],
        argument_set_inner_trivia=[empty_line],
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "{\n" in rebuilt

    func = FunctionDefinition(
        argument_set=[],
        argument_set_inner_trivia=[Comment(text="a\nb")],
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "# a" in rebuilt


def test_function_definition_render_empty_args_with_non_comment_trivia():
    """Drop inline formatting when inner trivia is not a comment."""
    func = FunctionDefinition(
        argument_set=[],
        argument_set_inner_trivia=[
            Assertion(expression=Primitive(value=True), body=Primitive(value=1))
        ],
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "assert" in rebuilt


def test_function_definition_render_empty_args_trailing_empty_lines(monkeypatch):
    """Append trailing empty lines in empty argument sets."""
    monkeypatch.setattr(func_def, "format_trivia", lambda *_args, **_kwargs: "# note")
    func = FunctionDefinition(
        argument_set=[],
        argument_set_inner_trivia=[Comment(text="note")],
        argument_set_trailing_empty_lines=2,
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "# note" in rebuilt
    assert "\n\n" in rebuilt


def test_function_definition_render_multiline_args_with_defaults():
    """Render multiline arguments with defaults and trailing comments."""
    default_on_newline = Identifier(
        name="a",
        default_value=Primitive(value=1),
        default_value_on_newline=True,
        default_value_indent=4,
    )
    default_inline = Identifier(
        name="b",
        default_value=AttributeSet(values=[]),
        default_value_on_newline=False,
    )
    trailing = Identifier(name="c")
    trailing.after = [Comment(text="inline", inline=True), Comment(text="tail")]

    func = FunctionDefinition(
        argument_set=[default_on_newline, default_inline, trailing],
        argument_set_is_multiline=True,
        argument_set_trailing_comment_indent=6,
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "\n" in rebuilt
    assert "c" in rebuilt


def test_function_definition_auto_multiline_defaults():
    """Exercise default-value multiline inference."""
    default_on_newline = Identifier(
        name="a",
        default_value=Primitive(value=1),
        default_value_on_newline=True,
        default_value_indent=2,
    )
    default_inline = Identifier(
        name="b",
        default_value=DummyExpr(text="x\ny"),
        default_value_on_newline=False,
    )
    func = FunctionDefinition(
        argument_set=[default_on_newline, default_inline],
        argument_set_is_multiline=None,
        output=Primitive(value=1),
    )
    assert "\n" in func.rebuild()


def test_function_definition_auto_multiline_default_inline():
    """Trigger multiline detection from inline default values."""
    default_inline = Identifier(
        name="b",
        default_value=DummyExpr(text="x\ny"),
        default_value_on_newline=False,
    )
    func = FunctionDefinition(
        argument_set=[default_inline],
        argument_set_is_multiline=None,
        output=Primitive(value=1),
    )
    assert "\n" in func.rebuild()


def test_function_definition_render_trailing_comma_logic():
    """Ensure leading commas suppress trailing commas."""
    first = Identifier(name="a")
    second = Identifier(name="b", before=[comma, linebreak])
    func = FunctionDefinition(
        argument_set=[first, second],
        argument_set_is_multiline=True,
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert "{\n" in rebuilt


def test_function_definition_format_colon_split_forced_newline():
    """Force the colon split onto a new line via comments."""
    func = FunctionDefinition(
        argument_set=Identifier(name="a"),
        before_colon_comments=[Comment(text="note")],
        output=Primitive(value=1),
    )
    rebuilt = func.rebuild()
    assert ": " in rebuilt


def test_function_definition_rebuild_scoped():
    """Scope-aware rebuilds should wrap with lets."""
    func = FunctionDefinition(
        argument_set=Identifier(name="a"),
        output=Primitive(value=1),
        scope=[AttributeSet(values=[])],
    )
    assert "let" in func.rebuild()


def test_function_definition_from_cst_missing_text():
    """Reject function definitions without text."""
    with pytest.raises(ValueError, match="Function definition has no code"):
        FunctionDefinition.from_cst(StubNode(type="function_expression", text=None))


def test_function_call_from_cst_errors():
    """Cover missing name/argument errors in function call parsing."""
    with pytest.raises(ValueError, match="Missing function name"):
        FunctionCall.from_cst(StubNode(type="apply_expression", text=None))

    node = StubNode(type="apply_expression", text=b"f x", children=[])
    with pytest.raises(ValueError, match="Missing function name"):
        FunctionCall.from_cst(node)

    node = StubNode(
        type="apply_expression",
        text=b"f x",
        field_map={
            "function": StubNode(type="identifier", text=None),
            "argument": StubNode(type="identifier", text=b"x"),
        },
    )
    with pytest.raises(ValueError, match="Missing function name"):
        FunctionCall.from_cst(node)


def test_function_call_from_cst_with_comments(monkeypatch):
    """Parse inline and block comments between function and argument."""
    monkeypatch.setattr(mapping, "tree_sitter_node_to_expression", lambda node: Primitive(value=1))

    function_node = StubNode(
        type="identifier",
        text=b"foo",
        start_byte=0,
        end_byte=3,
        start_point=DummyPoint(row=0, column=0),
        end_point=DummyPoint(row=0, column=3),
    )
    inline_comment = StubNode(
        type="comment",
        text=b"# inline",
        start_byte=4,
        end_byte=12,
        start_point=DummyPoint(row=0, column=4),
        end_point=DummyPoint(row=0, column=12),
    )
    between_comment = StubNode(
        type="comment",
        text=b"# between",
        start_byte=13,
        end_byte=22,
        start_point=DummyPoint(row=1, column=0),
        end_point=DummyPoint(row=1, column=9),
    )
    argument_node = StubNode(
        type="identifier",
        text=b"bar",
        start_byte=23,
        end_byte=26,
        start_point=DummyPoint(row=2, column=0),
        end_point=DummyPoint(row=2, column=3),
    )
    node = StubNode(
        type="apply_expression",
        text=b" " * 50,
        children=[function_node, inline_comment, between_comment, argument_node],
        field_map={"function": function_node, "argument": argument_node},
    )
    expr = FunctionCall.from_cst(node)
    assert expr.function_after
    assert expr.argument.before


def test_function_call_rebuild_trivia_and_rec():
    """Exercise call rebuild comment handling and rec injection."""
    func = FunctionCall(
        name="foo",
        argument=Primitive(value=1),
        function_after=[Comment(text="inline", inline=True), Comment(text="block")],
        argument_gap=None,
        recursive=True,
    )
    rebuilt = func.rebuild(indent=2)
    assert "rec" in rebuilt


def test_function_call_argument_layouts():
    """Exercise argument gap handling branches."""
    arg = DummyExpr(text="x\n", before=[linebreak])
    func = FunctionCall(name="foo", argument=arg, argument_gap=None)
    rebuilt = func.rebuild(indent=2)
    assert "\n" in rebuilt

    arg = DummyExpr(text="x", before=[linebreak])
    func = FunctionCall(name="foo", argument=arg, argument_gap="\n")
    rebuilt = func.rebuild(indent=2)
    assert "\n" in rebuilt
