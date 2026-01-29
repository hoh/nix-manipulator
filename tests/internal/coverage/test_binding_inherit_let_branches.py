"""Cover binding, inherit, and let branches that are hard to hit indirectly."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nix_manipulator import parser
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.binding_parser import parse_binding_sequence
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.let import LetExpression, parse_let_expression
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.trivia import gap_has_newline_from_offsets


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


def parse_let(source: str) -> LetExpression:
    """Parse a let-expression directly from the CST."""
    root = parser.parse_to_ast(source)
    let_node = next(child for child in root.children if child.type == "let_expression")
    return LetExpression.from_cst(let_node)


def test_parse_binding_sequence_inline_comment():
    """Inline comments after bindings should be attached to the binding."""
    expr = parse_expr("{ a = 1; # inline\n}")
    assert isinstance(expr, AttributeSet)
    binding = expr.values[0]
    assert isinstance(binding, Binding)
    assert any(isinstance(item, Comment) and item.inline for item in binding.after)


def test_binding_dict_coercion():
    """Dict values should become AttributeSets."""
    binding = Binding(name="a", value={"b": 1})
    assert isinstance(binding.value, AttributeSet)
    assert any(
        item.name == "b" for item in binding.value.values if isinstance(item, Binding)
    )


def test_gap_has_newline_from_offsets_with_source():
    """Exercise gap newline detection when source bytes are available."""
    node = StubNode(type="stub", text=b"foo\nbar", start_byte=0, end_byte=7)
    assert gap_has_newline_from_offsets(node, 0, 7) is True
    assert gap_has_newline_from_offsets(node, 0, 3) is False


def test_parse_binding_sequence_rejects_unknown_child():
    """Unsupported nodes in binding sequences should raise."""
    parent = StubNode(type="binding_set", text=b"")
    bad_child = StubNode(type="oops")
    with pytest.raises(ValueError, match="Unsupported child node"):
        parse_binding_sequence(parent, [bad_child])


def test_binding_from_cst_errors():
    """Cover error paths in binding parsing."""
    with pytest.raises(ValueError, match="Binding has no code"):
        Binding.from_cst(StubNode(type="binding", text=None))

    node = StubNode(
        type="binding",
        text=b"=;",
        children=[StubNode(type="="), StubNode(type=";")],
    )
    with pytest.raises(ValueError, match="Could not parse binding"):
        Binding.from_cst(node)


def test_binding_from_cst_comment_variants():
    """Parse bindings with after-equals, inline, and trailing comments."""
    source = """
{
  a = # eq
    1 # inline
  # trailing
  ;
}
""".strip()
    expr = parse_expr(source)
    binding = expr.values[0]
    assert isinstance(binding, Binding)
    assert any(
        isinstance(item, Comment) and item.text.strip() == "eq"
        for item in binding.value.before
    )
    assert any(
        isinstance(item, Comment) and item.inline for item in binding.value.after
    )
    assert any(
        isinstance(item, Comment) and not item.inline for item in binding.value.after
    )
    assert binding.value_gap


def test_binding_from_cst_leading_comment():
    """Ensure leading comments do not break binding parsing."""
    comment = StubNode(
        type="comment",
        text=b"# c",
        start_byte=0,
        end_byte=3,
        start_point=DummyPoint(row=0, column=0),
        end_point=DummyPoint(row=0, column=3),
    )
    attr = StubNode(
        type="attrpath",
        text=b"a",
        start_byte=4,
        end_byte=5,
        start_point=DummyPoint(row=0, column=4),
        end_point=DummyPoint(row=0, column=5),
    )
    equals = StubNode(type="=", start_byte=6, end_byte=7)
    value = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=8,
        end_byte=9,
        start_point=DummyPoint(row=0, column=8),
        end_point=DummyPoint(row=0, column=9),
    )
    semi = StubNode(type=";", start_byte=9, end_byte=10)
    node = StubNode(
        type="binding",
        text=b"# c a = 1;",
        children=[comment, attr, equals, value, semi],
    )
    binding = Binding.from_cst(node)
    assert binding.name == "a"


def test_binding_from_cst_comment_after_equals_newline():
    """Trigger newline-after-equals handling."""
    source = "{ a =\n  # after\n  1; }"
    expr = parse_expr(source)
    binding = expr.values[0]
    assert "\n" in binding.value_gap


def test_binding_rebuild_scoped():
    """Bindings with scope metadata should rebuild using let wrappers."""
    scoped = Binding(
        name="a",
        value=1,
        scope=[Binding(name="b", value=2)],
    )
    assert "let" in scoped.rebuild()


def test_binding_rebuild_semicolon_layout_and_linebreak_trivia():
    """Exercise semicolon placement and explicit linebreak trivia."""
    value_expr = Primitive(value=1)
    value_expr.before = [Comment(text="eq")]
    value_expr.after = [
        Comment(text="inline", inline=True),
        Comment(text="trail"),
    ]
    binding = Binding(
        name="a",
        value=value_expr,
        value_gap="\n  ",
    )
    rebuilt = binding.rebuild(indent=2)
    assert "# eq" in rebuilt
    assert "; # inline" in rebuilt
    assert "# trail" in rebuilt

    inline_semicolon = Binding(name="b", value=1)
    assert inline_semicolon.rebuild() == "b = 1;"

    with_linebreak = Binding(
        name="c",
        value=1,
        after=[linebreak, Comment(text="tail")],
    )
    assert "tail" in with_linebreak.rebuild()


def test_binding_rebuild_value_trailing_newline():
    """Ensure trailing newlines in values are handled."""
    value_expr = DummyExpr(text="1\n")
    binding = Binding(name="d", value=value_expr)
    assert binding.rebuild() == "d = 1;"


def test_inherit_from_cst_with_comments_and_strings():
    """Parse inherit with inline/trailing comments and quoted names."""
    source = """
{
  inherit (lib) foo # inline
    "bar" # trailing
    ;
}
""".strip()
    expr = parse_expr(source)
    assert isinstance(expr, AttributeSet)
    inherit = expr.values[0]
    assert isinstance(inherit, Inherit)
    assert len(inherit.names) == 2
    assert any(
        isinstance(item, Comment) and item.inline for item in inherit.names[0].after
    )


def test_inherit_rebuild_multiline_and_scoped():
    """Cover multiline rendering and scoped rebuild paths."""
    dummy_source = DummyExpr(text="src\n", before=[linebreak])
    name = Primitive(value="name")
    name.before = [empty_line, Comment(text="note")]
    inherit = Inherit(
        names=[name],
        from_expression=dummy_source,
        after_inherit_gap="\n",
        parenthesis_open_gap="\n",
        parenthesis_close_gap="\n",
        after_expression_gap="\n",
        name_gaps=["\n"],
        after_names_gap="\n",
    )
    rebuilt = inherit.rebuild(indent=2)
    assert "\n" in rebuilt

    no_names = Inherit(names=[], from_expression=None)
    assert "inherit" in no_names.rebuild()

    scoped = Inherit(
        names=[Primitive(value="x")],
        scope=[Binding(name="a", value=1)],
    )
    assert "let" in scoped.rebuild()


def test_inherit_from_cst_leading_and_trailing_comments():
    """Preserve leading and trailing comments around inherit names."""
    inherit_node = StubNode(type="inherit", start_byte=0, end_byte=7)
    leading_comment = StubNode(
        type="comment",
        text=b"# lead",
        start_byte=8,
        end_byte=15,
        start_point=DummyPoint(row=0, column=8),
        end_point=DummyPoint(row=0, column=14),
    )
    name1 = StubNode(
        type="identifier",
        text=b"foo",
        start_byte=20,
        end_byte=23,
        start_point=DummyPoint(row=1, column=2),
        end_point=DummyPoint(row=1, column=5),
    )
    between_comment = StubNode(
        type="comment",
        text=b"# mid",
        start_byte=24,
        end_byte=29,
        start_point=DummyPoint(row=2, column=0),
        end_point=DummyPoint(row=2, column=5),
    )
    name2 = StubNode(
        type="identifier",
        text=b"bar",
        start_byte=30,
        end_byte=33,
        start_point=DummyPoint(row=3, column=2),
        end_point=DummyPoint(row=3, column=5),
    )
    trailing_comment = StubNode(
        type="comment",
        text=b"# tail",
        start_byte=34,
        end_byte=40,
        start_point=DummyPoint(row=4, column=0),
        end_point=DummyPoint(row=4, column=6),
    )
    inherited_attrs = StubNode(
        type="inherited_attrs",
        start_byte=20,
        end_byte=40,
        children=[name1, between_comment, name2, trailing_comment],
    )
    semicolon = StubNode(type=";", start_byte=41, end_byte=42)
    node = StubNode(
        type="inherit",
        text=b"",
        children=[inherit_node, leading_comment, inherited_attrs, semicolon],
        start_byte=0,
        end_byte=42,
    )
    inherit = Inherit.from_cst(node)
    assert inherit.names
    assert any(isinstance(item, Comment) for item in inherit.names[0].before)
    assert any(isinstance(item, Comment) for item in inherit.names[1].before)
    assert any(isinstance(item, Comment) for item in inherit.names[1].after)


def test_inherit_from_cst_rejects_unknown_attr_type():
    """Reject unsupported inherit attribute types."""

    class ShiftyNode:
        def __init__(self):
            self._calls = 0
            self.text = b"bad"
            self.start_byte = 8
            self.end_byte = 9
            self.start_point = DummyPoint(row=0, column=0)
            self.end_point = DummyPoint(row=0, column=1)

        @property
        def type(self) -> str:
            self._calls += 1
            if self._calls <= 2:
                return "identifier"
            return "integer_expression"

    inherit_node = StubNode(type="inherit", start_byte=0, end_byte=7)
    bad_child = ShiftyNode()
    inherited_attrs = StubNode(
        type="inherited_attrs",
        start_byte=8,
        end_byte=9,
        children=[bad_child],
    )
    node = StubNode(
        type="inherit",
        text=b"",
        children=[inherit_node, inherited_attrs],
    )
    with pytest.raises(ValueError, match="Unsupported inherit attr type"):
        Inherit.from_cst(node)


def test_inherit_from_cst_semicolon_gap_without_names():
    """Fall back to paren/expression nodes when no names are present."""
    inherit_node = StubNode(type="inherit", start_byte=0, end_byte=7)
    open_paren = StubNode(type="(", start_byte=8, end_byte=9)
    from_node = StubNode(
        type="variable_expression",
        text=b"src",
        start_byte=9,
        end_byte=12,
    )
    close_paren = StubNode(type=")", start_byte=12, end_byte=13)
    semicolon = StubNode(type=";", start_byte=13, end_byte=14)
    node = StubNode(
        type="inherit_from",
        text=b"",
        children=[inherit_node, open_paren, from_node, close_paren, semicolon],
        field_map={"expression": from_node},
    )
    inherit = Inherit.from_cst(node)
    assert inherit.after_names_gap == ""

    node = StubNode(
        type="inherit_from",
        text=b"",
        children=[inherit_node, from_node, semicolon],
        field_map={"expression": from_node},
    )
    inherit = Inherit.from_cst(node)
    assert inherit.after_names_gap == ""


def test_inherit_rebuild_multiline_chunk_and_semicolon():
    """Avoid double newlines and keep semicolons aligned."""
    name1 = Primitive(value="a")
    name1.after = [empty_line]
    name2 = Primitive(value="b")
    name2.after = [empty_line]
    inherit = Inherit(names=[name1, name2], from_expression=None)
    rebuilt = inherit.rebuild(indent=2)
    assert "\n    ;" in rebuilt


def test_inherit_rebuild_multiline_comment_requires_multiline():
    """Force multiline output when comments precede inherit names."""
    name = Primitive(value="a")
    name.before = [Comment(text="note")]
    inherit = Inherit(names=[name], from_expression=None)
    rebuilt = inherit.rebuild(indent=0)
    assert "# note" in rebuilt


def test_inherit_rebuild_force_newline_indent():
    """Honor open-paren indentation when forcing multiline inherit sources."""
    dummy_source = DummyExpr(text="src\n")
    inherit = Inherit(
        names=[],
        from_expression=dummy_source,
        after_inherit_gap=" ",
        parenthesis_open_gap="\n",
        parenthesis_close_gap="",
        after_expression_gap=" ",
    )
    rebuilt = inherit.rebuild(indent=0)
    assert "\n" in rebuilt


def test_let_from_cst_errors():
    """Cover missing-token errors in let parsing."""
    with pytest.raises(ValueError, match="Attribute set has no code"):
        LetExpression.from_cst(StubNode(type="let_expression", text=None))

    node = StubNode(type="let_expression", text=b"let", children=[])
    with pytest.raises(ValueError, match="Could not parse let expression"):
        LetExpression.from_cst(node)

    node = StubNode(
        type="let_expression",
        text=b"let in",
        children=[StubNode(type="let"), StubNode(type="in")],
    )
    with pytest.raises(ValueError, match="Could not parse let body"):
        LetExpression.from_cst(node)

    node = StubNode(
        type="let_expression",
        text=b"let in",
        children=[
            StubNode(type="let", start_byte=0, end_byte=3),
            StubNode(type="comment", text=b"# c", start_byte=4, end_byte=7),
            StubNode(type="in", start_byte=8, end_byte=10),
        ],
    )
    with pytest.raises(ValueError, match="Could not parse let body"):
        LetExpression.from_cst(node)


def test_let_from_cst_with_comments():
    """Capture let comments before/after bindings and values."""
    source = """
let # after let
  a = 1;
  # post-binding
in
  # pre-value
  2 # inline
# trailing
"""
    expr = parse_let(source)
    assert expr.after_let_comment is not None
    assert expr.value.before


def test_let_from_cst_comment_outside_binding_range():
    """Ignore comments that fall outside the let/binding gap."""
    let_symbol = StubNode(type="let", start_byte=0, end_byte=3)
    binding_set = StubNode(
        type="binding_set",
        start_byte=4,
        end_byte=8,
        children=[],
    )
    in_symbol = StubNode(type="in", start_byte=12, end_byte=14)
    comment = StubNode(
        type="comment",
        text=b"# out",
        start_byte=9,
        end_byte=11,
        start_point=DummyPoint(row=1, column=0),
        end_point=DummyPoint(row=1, column=5),
    )
    body = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=15,
        end_byte=16,
        start_point=DummyPoint(row=2, column=0),
        end_point=DummyPoint(row=2, column=1),
    )
    node = StubNode(
        type="let_expression",
        text=b"let in 1",
        children=[let_symbol, binding_set, comment, in_symbol, body],
        field_map={"body": body},
    )
    expr = LetExpression.from_cst(node)
    assert expr.value.rebuild().strip() == "1"


def test_let_from_cst_trailing_comments_inline():
    """Ensure trailing comments are attached to the let body."""
    let_symbol = StubNode(type="let", start_byte=0, end_byte=3)
    in_symbol = StubNode(type="in", start_byte=4, end_byte=6)
    value_node = StubNode(
        type="integer_expression",
        text=b"1",
        start_byte=7,
        end_byte=8,
        start_point=DummyPoint(row=0, column=7),
        end_point=DummyPoint(row=0, column=8),
    )
    comment_node = StubNode(
        type="comment",
        text=b"# trailing",
        start_byte=8,
        end_byte=18,
        start_point=DummyPoint(row=0, column=8),
        end_point=DummyPoint(row=0, column=18),
    )
    node = StubNode(
        type="let_expression",
        text=b"let in 1# trailing",
        children=[let_symbol, in_symbol, value_node, comment_node],
        field_map={"body": value_node},
    )
    expr = LetExpression.from_cst(node)
    assert expr.value.after


def test_let_from_cst_blank_lines():
    """Preserve blank lines around bindings and body."""
    source = """
let

  a = 1;

in

  2
"""
    expr = parse_let(source)
    assert expr.local_variables[0].before
    assert expr.local_variables[-1].after
    assert expr.value.before


def test_scoped_let_preserves_attrpath_order():
    """Preserve attrpath binding order/trivia when rebuilding scoped lets."""
    source = """
let
  a.b = 1;

in
a
""".strip("\n")
    root = parser.parse_to_ast(source)
    let_node = next(child for child in root.children if child.type == "let_expression")
    scoped_expr = parse_let_expression(let_node)
    assert scoped_expr.rebuild() == source


def test_scoped_let_preserves_attrpath_order_with_nested_key():
    """Ensure attrpath order is preserved when the root key is named 'nested'."""
    source = """
let
  nested.b = 1;
  nested.a = 2;

in
nested
""".strip("\n")
    root = parser.parse_to_ast(source)
    let_node = next(child for child in root.children if child.type == "let_expression")
    scoped_expr = parse_let_expression(let_node)
    assert scoped_expr.rebuild() == source


def test_let_rebuild_inline_comment_spacing():
    """Ensure inline trailing comments keep spacing when rebuilding."""
    comment = Comment(text="inline", inline=True)
    dummy = DummyExpr(text=f"1{comment.rebuild(indent=0)}", after=[comment])
    let_expr = LetExpression(local_variables=[], value=dummy)
    rebuilt = let_expr.rebuild()
    assert "1 # inline" in rebuilt

    let_expr.after = [Comment(text="after", inline=True)]
    assert "after" in let_expr.rebuild()


def test_let_inline_comment_after_let():
    """Render inline comments attached to the let keyword."""
    let_expr = LetExpression(
        local_variables=[],
        value=Primitive(value=1),
        after_let_comment=Comment(text="note", inline=True),
    )
    rebuilt = let_expr.rebuild()
    assert "let # note" in rebuilt


def test_let_inline_comment_spacing_for_value():
    """Insert a space before inline comments in body strings."""
    value_expr = DummyExpr(text="1# c\n")
    value_expr.after = [Comment(text="c", inline=True)]
    let_expr = LetExpression(local_variables=[], value=value_expr)
    rebuilt = let_expr.rebuild()
    assert "1 # c" in rebuilt


def test_let_inline_comment_spacing_no_change():
    """Leave existing spacing intact when inline comments already have space."""
    value_expr = DummyExpr(text="1 # c\n")
    value_expr.after = [Comment(text="c", inline=True)]
    let_expr = LetExpression(local_variables=[], value=value_expr)
    rebuilt = let_expr.rebuild()
    assert "1 # c" in rebuilt


def test_let_to_scoped_expression_and_dict_access():
    """Cover scope lifting and dict-like access paths."""
    binding = Binding(name="a", value=1)
    inner = Primitive(value=2, scope=[binding])
    let_expr = LetExpression(local_variables=[binding], value=inner)
    scoped = let_expr.to_scoped_expression()
    assert bool(scoped.scope)

    assert let_expr["a"] == 1
    let_expr["a"] = 3
    assert let_expr["a"] == 3
    let_expr["b"] = 4
    del let_expr["b"]
    with pytest.raises(KeyError):
        _ = let_expr["missing"]
    with pytest.raises(KeyError):
        del let_expr["missing"]

    root = parser.parse_to_ast("let a = 1; in 2")
    let_node = next(child for child in root.children if child.type == "let_expression")
    scoped_expr = parse_let_expression(let_node)
    assert bool(scoped_expr.scope)
