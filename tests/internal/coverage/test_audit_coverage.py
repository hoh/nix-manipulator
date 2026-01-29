"""Targeted coverage for audit-critical branches and helpers."""

from __future__ import annotations

import code as code_module
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from nix_manipulator import parser
from nix_manipulator.__main__ import main as nima_main
from nix_manipulator.expressions import NixSourceCode
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import NixExpression, coerce_expression
from nix_manipulator.expressions.float import FloatExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.indented_string import IndentedString
from nix_manipulator.expressions.layout import comma, empty_line, linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.operator import Operator
from nix_manipulator.expressions.path import NixPath
from nix_manipulator.expressions.primitive import (
    IntegerPrimitive,
    NullPrimitive,
    Primitive,
    StringPrimitive,
)
from nix_manipulator.expressions.raw import RawExpression
from nix_manipulator.mapping import (
    EXPRESSION_TYPES,
    TREE_SITTER_TYPE_TO_EXPRESSION,
    register_expression,
    tree_sitter_node_to_expression,
)
from nix_manipulator.utils import pretty_print_cst


@dataclass
class DummyPoint:
    row: int = 0
    column: int = 0


@dataclass
class DummyNode:
    type: str
    text: bytes | None = None
    children: list["DummyNode"] = field(default_factory=list)
    start_byte: int = 0
    end_byte: int = 0
    start_point: DummyPoint = field(default_factory=DummyPoint)
    end_point: DummyPoint = field(default_factory=DummyPoint)

    def child_by_field_name(self, _name: str) -> None:
        return None


def test_pretty_print_cst_handles_known_types():
    """Cover pretty_print_cst branches for expression, list, and source nodes."""
    primitive = Primitive(value="hello")
    assert "Primitive" in pretty_print_cst(primitive)

    # Construct a simple list expression using NixList to exercise that branch.
    list_obj = NixList(value=[Primitive(value=1)])
    assert "NixList" in pretty_print_cst(list_obj)

    source = parser.parse("1")
    rendered = pretty_print_cst(source)
    assert "NixSourceCode" in rendered

    empty_source = parser.parse("")
    assert "NixSourceCode" in pretty_print_cst(empty_source)


def test_pretty_print_cst_unknown_type_raises():
    """Reject unknown node types for safer debugging output."""
    with pytest.raises(ValueError, match="Unknown node type"):
        pretty_print_cst(object())


def test_main_shell_injects_source(monkeypatch, tmp_path):
    """Exercise the __main__ shell path without invoking an interactive prompt."""
    file_path = tmp_path / "input.nix"
    file_path.write_text("1", encoding="utf-8")

    captured = {}

    def fake_interact(*, banner, local):
        captured["banner"] = banner
        captured["locals"] = local

    monkeypatch.setattr(code_module, "interact", fake_interact)

    result = nima_main(["shell", "-f", str(file_path)])
    assert result == 0
    assert captured["banner"].startswith("Nix Manipulator shell")
    assert captured["locals"]["source_text"] == "1"
    assert isinstance(captured["locals"]["source"], NixSourceCode)


def test_main_module_exits_with_help(monkeypatch):
    """Cover the module entrypoint and help fallback behavior."""
    monkeypatch.setattr(sys, "argv", ["nima"])
    sys.modules.pop("nix_manipulator.__main__", None)
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("nix_manipulator.__main__", run_name="__main__")
    assert exc_info.value.code == 2


def test_main_test_rejects_parse_errors(tmp_path, capsys):
    """Fail fast when input cannot be parsed into a valid CST."""
    file_path = tmp_path / "bad.nix"
    file_path.write_text("{ foo = ; }", encoding="utf-8")

    result = nima_main(["test", "-f", str(file_path)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out.strip() == "Fail"


def test_parser_load_language_branches(monkeypatch):
    """Cover _load_language paths for Language and capsule inputs."""
    original_language = parser.ts_nix.language
    language_obj = parser.NIX_LANGUAGE
    monkeypatch.setattr(parser.ts_nix, "language", lambda: language_obj)
    assert parser._load_language() is language_obj

    pointer = original_language()
    if isinstance(pointer, int):
        capsule = parser._capsule_from_pointer(pointer)
    else:
        try:
            pointer_value = int(pointer)
        except (TypeError, ValueError):
            capsule = pointer
        else:
            capsule = parser._capsule_from_pointer(pointer_value)
    monkeypatch.setattr(parser.ts_nix, "language", lambda: capsule)
    assert parser._load_language().__class__.__name__ == "Language"


def test_parse_file_accepts_path(tmp_path):
    """Ensure parse_file reads Path inputs with UTF-8 for parsing."""
    file_path = tmp_path / "input.nix"
    file_path.write_text("{ a = 1; }", encoding="utf-8")
    source = parser.parse_file(Path(file_path))
    assert source.rebuild().strip() == "{ a = 1; }"


def test_mapping_register_expression_and_unknown_node():
    """Exercise expression registration and unknown node failures."""

    class DummyExpression(NixExpression):
        tree_sitter_types = {"dummy_expression"}

        @classmethod
        def from_cst(cls, node):
            raise AssertionError("not used")

        def rebuild(self, indent: int = 0, inline: bool = False) -> str:
            return "dummy"

    try:
        register_expression(DummyExpression)
        assert TREE_SITTER_TYPE_TO_EXPRESSION["dummy_expression"] is DummyExpression
    finally:
        TREE_SITTER_TYPE_TO_EXPRESSION.pop("dummy_expression", None)
        EXPRESSION_TYPES.discard(DummyExpression)

    with pytest.raises(ValueError, match="Unsupported node type"):
        tree_sitter_node_to_expression(SimpleNamespace(type="unknown"))


def test_layout_repr_sentinels():
    """Cover sentinel __repr__ implementations for layout markers."""
    assert repr(empty_line) == "EmptyLine"
    assert repr(linebreak) == "Linebreak"
    assert repr(comma) == "Comma"


def test_expression_base_helpers_and_coercion():
    """Exercise base expression helpers and coercion errors."""

    class DummyExpr(NixExpression):
        def rebuild(self, indent: int = 0, inline: bool = False) -> str:
            return "dummy"

    expr = DummyExpr(
        scope_state={
            "stack": [
                {
                    "scope": [],
                    "body_before": [],
                    "body_after": [],
                    "attrpath_order": [],
                    "after_let_comment": None,
                }
            ],
        }
    )
    assert not expr.scope_state.stack
    with pytest.raises(NotImplementedError):
        NixExpression().rebuild()
    with pytest.raises(NotImplementedError):
        NixExpression.from_cst(DummyNode(type="noop"))

    rebuilt = expr.add_trivia("x", indent=0, inline=False, after_str="tail")
    assert rebuilt == "x\ntail"

    float_expr = coerce_expression(1.5)
    assert isinstance(float_expr, FloatExpression)
    assert float_expr.rebuild() == "1.5"

    null_expr = coerce_expression(None)
    assert isinstance(null_expr, NullPrimitive)
    assert null_expr.rebuild() == "null"

    with pytest.raises(ValueError, match="float must be finite"):
        coerce_expression(float("inf"))

    with pytest.raises(ValueError, match="Unsupported expression type"):
        coerce_expression({"unsupported": True})


def test_primitive_operator_helpers_and_dispatch():
    """Cover primitive operator helpers and subclass dispatch paths."""
    int_primitive = Primitive(value=1)
    other_int = Primitive(value=2)
    assert isinstance(int_primitive, IntegerPrimitive)
    assert isinstance(other_int, IntegerPrimitive)

    summed = int_primitive + other_int
    assert isinstance(summed, IntegerPrimitive)
    assert summed == 3

    left_added = 2 + int_primitive
    assert isinstance(left_added, IntegerPrimitive)
    assert left_added == 3

    int_primitive += True
    assert int_primitive == 2

    with pytest.raises(TypeError):
        _ = int_primitive + "oops"

    identifier = Identifier(name="foo")
    assert int_primitive != identifier
    assert repr(int_primitive) == "2"

    str_primitive = Primitive(value="foo")
    assert isinstance(str_primitive, StringPrimitive)
    assert str_primitive + "bar" == "foobar"
    assert str_primitive.__radd__("bar") == "barfoo"
    with pytest.raises(TypeError):
        _ = str_primitive + 5

    null_primitive = Primitive(value=None)
    assert isinstance(null_primitive, NullPrimitive)
    assert null_primitive == None  # noqa: E711


def test_operator_and_path_from_cst_errors():
    """Cover from_cst error branches for operators and paths."""
    assert Operator.from_cst(DummyNode(type="operator", text=b"+")).name == "+"
    with pytest.raises(ValueError, match="Missing operator"):
        Operator.from_cst(DummyNode(type="operator", text=None))
    with pytest.raises(ValueError, match="Path is missing"):
        NixPath.from_cst(DummyNode(type="path_expression", text=None))


def test_operator_and_path_rebuild_with_scope():
    """Ensure scope-aware rebuilds pass through for simple expressions."""
    operator = Operator(
        name="+", scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in operator.rebuild()

    path = NixPath(
        path="./foo", scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in path.rebuild()


def test_float_expression_parsing_and_rebuild():
    """Validate float parsing, rebuild, and error handling."""
    node = DummyNode(type="float_expression", text=b"1.25")
    parsed = FloatExpression.from_cst(node)
    assert parsed.rebuild() == "1.25"
    assert repr(parsed) == "1.25"

    scoped = FloatExpression(
        value="1.25", scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in scoped.rebuild()

    with pytest.raises(ValueError, match="Missing expression"):
        FloatExpression.from_cst(DummyNode(type="float_expression", text=None))


def test_indented_string_parsing_and_rebuild():
    """Exercise indented string parsing branches and rebuild output."""
    node = DummyNode(type="indented_string_expression", text=b"''hello''")
    parsed = IndentedString.from_cst(node)
    assert parsed.rebuild() == "''hello''"
    assert parsed.raw_string

    raw_node = DummyNode(type="indented_string_expression", text=b"raw")
    parsed_raw = IndentedString.from_cst(raw_node)
    assert parsed_raw.value == "raw"
    assert parsed_raw.raw_string

    escaped = IndentedString(value="a''b")
    assert escaped.rebuild() == "''a'''b''"

    with pytest.raises(
        ValueError, match="Indented string cannot end with a single quote"
    ):
        IndentedString(value="ends'").rebuild()

    scoped = IndentedString(
        value="hello", scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in scoped.rebuild()

    with pytest.raises(ValueError, match="Missing expression"):
        IndentedString.from_cst(DummyNode(type="indented_string_expression", text=None))


def test_raw_expression_rebuild_variants():
    """Cover raw expression rebuild for scoped and trivia paths."""
    raw = RawExpression(text="raw")
    assert raw.rebuild() == "raw"

    raw_with_trivia = RawExpression(text="raw", before=[empty_line])
    assert "raw" in raw_with_trivia.rebuild()

    raw_scoped = RawExpression(
        text="raw", scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in raw_scoped.rebuild()


def test_identifier_defaults_and_trivia():
    """Cover identifier default formatting and trimming behavior."""
    with pytest.raises(ValueError, match="Identifier has no name"):
        Identifier.from_cst(DummyNode(type="identifier", text=None))

    default_expr = Primitive(value="x")
    identifier = Identifier(
        name="foo",
        default_value=default_expr,
        after_question=[Comment(text="c", inline=True)],
    )
    rendered = identifier.rebuild(indent=0, inline=False)
    assert "foo ?" in rendered

    identifier_newline = Identifier(
        name="bar",
        default_value=Primitive(value=1),
        default_value_on_newline=True,
        default_value_indent=4,
        before=[linebreak],
    )
    rendered_newline = identifier_newline.rebuild(indent=0, inline=False)
    assert "bar ?" in rendered_newline and "\n" in rendered_newline


def test_primitive_from_cst_and_rebuild_branches():
    """Cover primitive parsing branches and rebuild error handling."""
    assert (
        Primitive.from_cst(DummyNode(type="string_expression", text=b'"x"')).value
        == "x"
    )
    assert (
        Primitive.from_cst(DummyNode(type="string_fragment", text=b"frag")).value
        == "frag"
    )
    assert (
        Primitive.from_cst(DummyNode(type="integer_expression", text=b"42")).value == 42
    )
    assert (
        Primitive.from_cst(DummyNode(type="variable_expression", text=b"true")).value
        is True
    )

    identifier = Primitive.from_cst(DummyNode(type="variable_expression", text=b"foo"))
    assert isinstance(identifier, Identifier)

    with pytest.raises(ValueError, match="Missing expression"):
        Primitive.from_cst(DummyNode(type="integer_expression", text=None))
    with pytest.raises(ValueError, match="Unsupported expression type"):
        Primitive.from_cst(DummyNode(type="weird", text=b"nope"))

    escaped = Primitive(value='a"b\\c\n')
    assert '\\"' in escaped.rebuild()

    escaped_controls = Primitive(value="a\r\t")
    assert "\\r" in escaped_controls.rebuild()
    assert "\\t" in escaped_controls.rebuild()

    scoped = Primitive(
        value=1, scope=[Binding(name="scoped", value=Primitive(value=0))]
    )
    assert "let" in scoped.rebuild()

    with pytest.raises(ValueError, match="Unsupported expression type"):
        Primitive(value=1.5).rebuild()


def test_comment_rendering_and_multiline_rebuild():
    """Cover comment parsing and multiline rebuild behavior."""
    with pytest.raises(ValueError, match="Missing comment"):
        Comment.from_cst(DummyNode(type="comment", text=None))

    shebang = Comment.from_cst(DummyNode(type="comment", text=b"#! /usr/bin/env bash"))
    assert shebang.shebang
    assert str(shebang).startswith("#!")

    hash_comment = Comment.from_cst(DummyNode(type="comment", text=b"#no-space"))
    assert hash_comment.space_after_hash is False

    block = Comment.from_cst(DummyNode(type="comment", text=b"/* hi */"))
    assert isinstance(block, MultilineComment)
    assert block.rebuild() == "/* hi */"

    indented = DummyNode(
        type="comment",
        text=b"/*\n  alpha\n  beta\n*/",
        start_point=DummyPoint(row=0, column=2),
    )
    indented_comment = Comment.from_cst(indented)
    assert isinstance(indented_comment, MultilineComment)
    assert "\n" in indented_comment.text

    trimmed_indent = Comment.from_cst(
        DummyNode(type="comment", text=b"/*\n    alpha\n    beta\n*/")
    )
    assert isinstance(trimmed_indent, MultilineComment)

    blank_block = Comment.from_cst(DummyNode(type="comment", text=b"/*\n\n*/"))
    assert isinstance(blank_block, MultilineComment)

    fallback = Comment.from_cst(DummyNode(type="comment", text=b"??"))
    assert fallback.text == "??"

    multiline = MultilineComment(text="\nline1\nline2", doc=True)
    rebuilt = multiline.rebuild(indent=2)
    assert rebuilt.startswith("  /**")
    assert "\n" in rebuilt

    inline_block = MultilineComment(text="line1\nline2", doc=False, inner_indent=1)
    assert inline_block.rebuild(indent=0).startswith("/* ")


def test_ellipses_scoped_rebuild():
    """Cover ellipses scoped rebuild path."""
    expr = Ellipses(scope=[Binding(name="scoped", value=Primitive(value=0))])
    assert "let" in expr.rebuild()
