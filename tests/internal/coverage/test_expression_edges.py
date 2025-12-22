"""Exercise expression edge cases that are hard to reach through fixtures."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from nix_manipulator import parser
from nix_manipulator.exceptions import NixSyntaxError
from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import coerce_expression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.has_attr import HasAttrExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.if_expression import IfExpression
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.raw import RawExpression
from nix_manipulator.expressions.scope import Scope
from nix_manipulator.expressions.select import Select
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.source_code import NixSourceCode
from nix_manipulator.expressions.unary import UnaryExpression
from nix_manipulator.expressions.with_statement import WithStatement


@dataclass
class DummyPoint:
    row: int = 0
    column: int = 0


@dataclass
class FieldNode:
    type: str
    text: bytes | None = None
    children: list["FieldNode"] = field(default_factory=list)
    field_map: dict[str, "FieldNode"] = field(default_factory=dict)
    start_byte: int = 0
    end_byte: int = 0
    start_point: DummyPoint = field(default_factory=DummyPoint)
    end_point: DummyPoint = field(default_factory=DummyPoint)

    def child_by_field_name(self, name: str) -> "FieldNode" | None:
        return self.field_map.get(name)


def parse_expr(source: str):
    """Parse and return the first top-level expression."""
    parsed = parser.parse(source)
    assert parsed.expressions
    return parsed.expressions[0]


def test_assertion_from_cst_error_paths():
    """Cover assertion parsing errors and missing fields."""
    with pytest.raises(ValueError, match="Identifier has no name"):
        Assertion.from_cst(FieldNode(type="assert_expression", text=None))

    with pytest.raises(ValueError, match="Assertion has no condition"):
        Assertion.from_cst(FieldNode(type="assert_expression", text=b"assert"))

    condition = FieldNode(type="variable_expression", text=b"true")
    node = FieldNode(
        type="assert_expression",
        text=b"assert true;",
        field_map={"condition": condition},
        children=[FieldNode(type="assert"), condition],
    )
    with pytest.raises(ValueError, match="Assertion has no body"):
        Assertion.from_cst(node)


def test_assertion_inline_trailing_comment_and_rebuild():
    """Capture trailing inline comments and rebuild with/without body."""
    expr = parse_expr("assert true; # trailing\n  1")
    assert isinstance(expr, Assertion)
    assert expr.after

    assert Assertion(expression=Primitive(value=True)).rebuild().startswith("assert")
    scoped = Assertion(
        expression=Primitive(value=True),
        body=Primitive(value=1),
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()


def test_assertion_comment_forces_newline_and_trims():
    """Force a newline when comments appear after assert."""
    condition = Primitive(value=True, before=[linebreak])
    assertion = Assertion(
        expression=condition,
        body=Primitive(value=1),
        after_assert_comments=[Comment(text="note")],
    )
    rebuilt = assertion.rebuild()
    assert rebuilt.startswith("assert  # note\n")
    assert "\n  true;" in rebuilt


def test_assertion_multiline_condition_breaks():
    """Break assert when condition has unindented inner lines."""
    assertion = Assertion(
        expression=RawExpression(text="foo\nbar\nbaz"),
        body=Primitive(value=1),
    )
    rebuilt = assertion.rebuild()
    assert rebuilt.startswith("assert\n")


def test_assertion_multiline_condition_absorbed():
    """Keep assert inline when multiline condition is absorbed."""
    assertion = Assertion(
        expression=RawExpression(text="foo\n  bar\nbaz"),
        body=Primitive(value=1),
    )
    rebuilt = assertion.rebuild()
    assert rebuilt.startswith("assert foo\n")


def test_has_attr_from_cst_errors():
    """Cover has-attr parsing errors for missing fields."""
    with pytest.raises(ValueError, match="Missing has-attr expression"):
        HasAttrExpression.from_cst(FieldNode(type="has_attr_expression", text=None))

    with pytest.raises(ValueError, match="Missing has-attr expression fields"):
        HasAttrExpression.from_cst(FieldNode(type="has_attr_expression", text=b"x"))

    expr_node = FieldNode(type="variable_expression", text=b"x")
    attr_node = FieldNode(type="attrpath", text=None)
    node = FieldNode(
        type="has_attr_expression",
        text=b"x ?",
        field_map={"expression": expr_node, "attrpath": attr_node},
        children=[expr_node, attr_node],
    )
    with pytest.raises(ValueError, match="Missing has-attr attrpath text"):
        HasAttrExpression.from_cst(node)


def test_has_attr_rebuild_forced_newlines():
    """Force newline layouts around the question mark during rebuild."""
    comment = Comment(text="note")
    expr = HasAttrExpression(
        expression=Primitive(value="foo"),
        attrpath="bar",
        left_gap=" ",
        right_gap=" ",
        before_question_comments=[comment, empty_line],
        after_question_comments=[comment],
    )
    rebuilt = expr.rebuild()
    assert "?" in rebuilt

    scoped = HasAttrExpression(
        expression=Primitive(value="foo"),
        attrpath="bar",
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()


def test_unary_from_cst_errors_and_rebuild():
    """Cover unary parsing errors and rebuild branches."""
    with pytest.raises(ValueError, match="Unsupported expression type"):
        UnaryExpression.from_cst(FieldNode(type="identifier", text=b"foo"))

    bad_node = FieldNode(type="unary_expression", text=b"-")
    with pytest.raises(ValueError, match="Unary expression is incomplete"):
        UnaryExpression.from_cst(bad_node)

    operator = FieldNode(type="operator", text=None)
    expr_node = FieldNode(type="integer_expression", text=b"1")
    bad_operator = FieldNode(
        type="unary_expression", text=b"-1", children=[operator, expr_node]
    )
    with pytest.raises(ValueError, match="Unary operator missing"):
        UnaryExpression.from_cst(bad_operator)

    expr = UnaryExpression(operator="-", expression=1)
    assert isinstance(expr.expression, Primitive)

    with_comment = UnaryExpression(
        operator="-",
        expression=Primitive(value=1),
        operand_gap=" ",
        between=[Comment(text="c")],
    )
    assert "\n" in with_comment.rebuild()

    plus_plus = UnaryExpression(operator="++", expression=Primitive(value=1))
    assert "\n" in plus_plus.rebuild()

    scoped = UnaryExpression(
        operator="-",
        expression=Primitive(value=1),
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()


def test_with_statement_rebuild_paths_and_errors():
    """Exercise with-statement rebuild branches and error paths."""
    with pytest.raises(ValueError, match="Missing text in with statement"):
        WithStatement.from_cst(FieldNode(type="with_expression", text=None))

    list_body = NixList(value=[Primitive(value=1), Primitive(value=2)], multiline=True)
    with_expr = WithStatement(
        environment=Primitive(value="env"),
        body=list_body,
        after_with_comments=[Comment(text="c")],
    )
    assert "\n" in with_expr.rebuild()

    inline_list = NixList(value=[Primitive(value=1)], multiline=False)
    inline_expr = WithStatement(
        environment=Primitive(value="env"),
        body=inline_list,
    )
    assert "with" in inline_expr.rebuild()

    absorbed = WithStatement(
        environment=Primitive(value="env"),
        body=Parenthesis(value=NixList(value=[Primitive(value=1)])),
    )
    assert "(" in absorbed.rebuild()

    scoped = WithStatement(
        environment=Primitive(value="env"),
        body=Primitive(value=1),
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()


def test_if_expression_inline_comments_and_rebuild():
    """Cover inline then/else comments and newline condition formatting."""
    expr = parse_expr("if true then # then\n  1 else # else\n  2")
    assert isinstance(expr, IfExpression)
    assert expr.after_then_comments
    assert expr.after_else_comments

    manual = IfExpression(
        condition=Primitive(value=True),
        consequence=Primitive(value=1),
        alternative=Primitive(value=2),
        condition_gap="\n  ",
    )
    assert "if" in manual.rebuild()

    scoped = IfExpression(
        condition=Primitive(value=True),
        consequence=Primitive(value=1),
        alternative=Primitive(value=2),
        scope=[Binding(name="scoped", value=Primitive(value=0))],
    )
    assert "let" in scoped.rebuild()


def test_parenthesis_errors_and_multiline_rebuild():
    """Cover parenthesis parsing errors and multiline rebuild."""
    with pytest.raises(ValueError, match="Parenthesis has no code"):
        Parenthesis.from_cst(FieldNode(type="parenthesized_expression", text=None))

    with pytest.raises(ValueError, match="Parenthesis is missing delimiters"):
        Parenthesis.from_cst(
            FieldNode(type="parenthesized_expression", text=b"()", children=[])
        )

    open_paren = FieldNode(type="(", start_byte=0, end_byte=1)
    close_paren = FieldNode(type=")", start_byte=1, end_byte=2)
    empty_node = FieldNode(
        type="parenthesized_expression",
        text=b"()",
        children=[open_paren, close_paren],
    )
    with pytest.raises(ValueError, match="Parenthesis contains no expression"):
        Parenthesis.from_cst(empty_node)

    expr = Parenthesis(
        value=Primitive(value=1),
        leading_gap="\n  ",
        trailing_gap="\n",
        leading_blank_line=True,
        trailing_blank_line=True,
    )
    assert "\n" in expr.rebuild()


def test_list_from_cst_error_and_rebuild_variants():
    """Cover list parsing errors and rebuild branches."""
    with pytest.raises(ValueError, match="List has no code"):
        NixList.from_cst(FieldNode(type="list_expression", text=None))

    empty_list = NixList(value=[], inner_trivia=[empty_line])
    assert "\n" in empty_list.rebuild()

    inline_list = NixList(value=[Primitive(value=1)])
    assert inline_list.simple_inline_preview(indent=0)

    multi_list = NixList(value=[Primitive(value=1), Primitive(value=2)])
    assert multi_list.simple_inline_preview(indent=0) is None


def test_select_errors_and_rebuild_branches():
    """Cover select parsing errors and default formatting."""
    with pytest.raises(ValueError, match="Select expression is missing"):
        Select.from_cst(FieldNode(type="select_expression", text=None))

    expr_node = FieldNode(type="variable_expression", text=b"x")
    with pytest.raises(ValueError, match="Select expression is missing required fields"):
        Select.from_cst(FieldNode(type="select_expression", text=b"x", field_map={}))

    attr_node = FieldNode(type="attrpath", text=None)
    node = FieldNode(
        type="select_expression",
        text=b"x.y",
        field_map={"expression": expr_node, "attrpath": attr_node},
    )
    with pytest.raises(ValueError, match="Select expression attrpath is missing"):
        Select.from_cst(node)

    inline_comment = Comment(text="inline", inline=True)
    block_comment = Comment(text="block")
    expr = Select(
        expression=NixList(value=[Primitive(value=1)], multiline=True),
        attribute="attr",
        default=Primitive(value=2),
        attr_gap="\n  ",
        default_gap="\n  ",
        default_before=[inline_comment, block_comment],
    )
    assert "or" in expr.rebuild()

    inline_default = Select(
        expression=Primitive(value="x"),
        attribute="attr",
        default=Primitive(value=2),
        default_gap=" ",
    )
    assert " or " in inline_default.rebuild()


def test_attribute_set_errors_and_rebuild_branches():
    """Cover attribute set errors and rebuild branches."""
    with pytest.raises(ValueError, match="Attribute set has no code"):
        AttributeSet.from_cst(FieldNode(type="attrset_expression", text=None))

    error_node = SimpleNamespace(type="ERROR")
    with pytest.raises(NixSyntaxError, match="ERROR node"):
        AttributeSet.from_cst(
            SimpleNamespace(text=b"{}", named_children=[error_node], children=[])
        )

    empty_set = AttributeSet(values=[], inner_trivia=[empty_line])
    assert "\n" in empty_set.rebuild()

    binding_value = AttributeSet.from_dict({"a": Primitive(value=1)}).values[0]
    multiline_set = AttributeSet(values=[binding_value])
    multiline_set.multiline = True
    assert "\n" in multiline_set.rebuild()

    inline_set = AttributeSet(values=[binding_value], multiline=False)
    assert inline_set.rebuild().strip().startswith("{")

    with pytest.raises(KeyError):
        _ = inline_set["missing"]
    inline_set["new"] = Primitive(value=2)
    del inline_set["new"]


def test_source_code_error_paths_and_eq():
    """Cover error handling, trailing trivia, and equality checks."""
    with pytest.raises(ValueError, match="Missing source text"):
        NixSourceCode.from_cst(SimpleNamespace(text=None))

    error_source = NixSourceCode.from_cst(
        SimpleNamespace(text=b"oops", has_error=True, children=[])
    )
    assert error_source.rebuild()

    fallback = NixSourceCode.from_cst(
        SimpleNamespace(
            type="source_code",
            text=b"oops",
            children=[SimpleNamespace(type="ERROR", children=[])],
        )
    )
    assert fallback.rebuild()

    trailing = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[Primitive(value=1)],
        trailing=[Comment(text="c")],
    )
    assert trailing.rebuild().endswith("# c")

    plain = NixSourceCode(
        node=SimpleNamespace(), expressions=[Primitive(value=1)]
    )
    assert plain == plain
    assert plain == Primitive(value=1)
    assert plain == plain.rebuild()
    assert plain != object()

    empty = NixSourceCode(node=SimpleNamespace(), expressions=[])
    empty["foo"] = Primitive(value=1)
    assert empty.rebuild() == "{ foo = 1; }"

    existing_set = AttributeSet(
        values=[
            Binding(name="foo", value=Primitive(value=1)),
            Binding(name="bar", value=Primitive(value=2)),
        ],
        multiline=False,
    )
    source_with_values = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[existing_set],
    )
    source_with_values["baz"] = Primitive(value=3)
    bindings = [
        binding.name for binding in existing_set.values if isinstance(binding, Binding)
    ]
    assert bindings == ["foo", "bar", "baz"]


def test_source_resolve_target_set_wrappers_and_errors():
    """Unwrap top-level wrappers to the editable attribute set."""
    with pytest.raises(ValueError, match="Source contains no expressions"):
        NixSourceCode(node=SimpleNamespace(), expressions=[])._resolve_target_set()

    with pytest.raises(ValueError, match="Top-level expression must be an attribute set"):
        NixSourceCode(node=SimpleNamespace(), expressions=[Primitive(value=1)])._resolve_target_set()

    bad_assertion = Assertion(expression=Primitive(value=True), body=None)
    with pytest.raises(ValueError, match="Unexpected assertion without body"):
        NixSourceCode(node=SimpleNamespace(), expressions=[bad_assertion])._resolve_target_set()

    let_source = parser.parse("let pkg = { value = 1; }; in pkg")
    assert isinstance(let_source._resolve_target_set(), AttributeSet)

    with_source = parser.parse("with env; { nested = 1; }")
    assert isinstance(with_source._resolve_target_set(), AttributeSet)

    call_source = parser.parse("let pkg = { nested = 1; }; in build pkg")
    assert isinstance(call_source._resolve_target_set(), AttributeSet)

    fn_output = FunctionDefinition(
        argument_set=Identifier(name="arg"),
        output=FunctionCall(
            name=Identifier(name="f"),
            argument=AttributeSet(values=[]),
        ),
    )
    fn_source = NixSourceCode(node=SimpleNamespace(), expressions=[fn_output])
    assert fn_source._resolve_target_set() is fn_output.output.argument

    paren_source = parser.parse("({ foo = 1; })")
    assert isinstance(paren_source._resolve_target_set(), AttributeSet)


def test_source_eq_rejects_contains_error_expression():
    """contains_error should short-circuit equality checks."""
    errored = NixSourceCode(
        node=SimpleNamespace(), expressions=[Primitive(value=1)], contains_error=True
    )
    assert not (errored == Primitive(value=1))
    assert not (errored == "1")


def test_source_delitem_preserves_trivia_and_structure():
    """Deleting the last binding should not drop surrounding trivia."""
    source = parser.parse("/* lead */ { foo = 1; }\n# tail")
    del source["foo"]
    rebuilt = source.rebuild()
    assert rebuilt.startswith("/* lead */")
    assert "{ }" in rebuilt
    assert rebuilt.strip().endswith("# tail")


def test_source_eq_respects_parse_errors():
    """Parse errors should not compare equal to valid expressions or text."""
    error_source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[RawExpression(text="bad")],
        contains_error=True,
    )
    same_error = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[RawExpression(text="bad")],
        contains_error=True,
    )
    ok_source = parser.parse("{ }")
    assert error_source == same_error
    assert error_source != ok_source
    assert error_source != "{ }"


def test_scope_access_and_mutations():
    """Cover Scope dict-style access and owner updates."""
    owner = AttributeSet(values=[], scope=[Binding(name="foo", value=1)])
    assert owner.scope["foo"] == 1
    owner.scope["foo"] = 3
    owner.scope["bar"] = 2
    with pytest.raises(KeyError):
        _ = owner.scope["missing"]
    with pytest.raises(KeyError):
        del owner.scope["missing"]
    del owner.scope["bar"]
    owner.scope[0] = Binding(name="foo", value=4)
    del owner.scope[0]

    orphan_scope = Scope()
    orphan_scope["alpha"] = 1
    assert orphan_scope[0].name == "alpha"
    assert coerce_expression(True).rebuild() == "true"


def test_source_code_preserves_trailing_newline():
    """Ensure EOF newlines are preserved for strict round-trips."""
    source = "{ foo = 1; }\n"
    parsed = parser.parse(source)
    assert parsed.rebuild() == source
