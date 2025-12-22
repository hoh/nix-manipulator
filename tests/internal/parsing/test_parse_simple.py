from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.parser import parse


def test_parse_let_statement():
    """Ensure let parsing captures scope for later edits."""
    source = """
let
  foo = "bar";
in
foo
""".strip("\n")
    assert parse(source) == Identifier(
        name="foo", scope=[Binding(name="foo", value="bar")]
    )


def test_parse_nix_function_definition_let_bindings():
    """Ensure let bindings inside functions are tracked for rebuild."""
    source = '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    assert (
        parse(source)
        == FunctionDefinition(
            argument_set=[],
            output=AttributeSet(
                values=[],
                scope=[
                    Binding(name="foo", value=Identifier(name="bar")),
                    Binding(name="alice", value="bob"),
                ],
            ),
        ).rebuild()
    )


def test_parse_function_definition_leading_commas():
    """Ensure leading-commas formals rebuild in RFC-166 style."""
    source = """
{ foo
, bar
, baz ? 1
}:
baz
""".strip("\n")
    expected = """
{
  foo,
  bar,
  baz ? 1,
}:
baz
""".strip("\n")
    assert parse(source).rebuild() == expected


def test_parse_nested_set():
    """Ensure nested sets are parsed correctly in both styles."""
    source = """
{
  foo.bar = "baz";
}
""".strip("\n")
    alternative = """
{
  foo = {
    bar = "baz";
  };
}
""".strip("\n")
    parsed_attrpath = parse(source).expr
    parsed_explicit = parse(alternative).expr

    assert isinstance(parsed_attrpath, AttributeSet)
    assert isinstance(parsed_explicit, AttributeSet)

    attr_binding = parsed_attrpath.values[0]
    explicit_binding = parsed_explicit.values[0]
    assert isinstance(attr_binding, Binding)
    assert isinstance(explicit_binding, Binding)
    assert attr_binding.name == explicit_binding.name == "foo"
    assert isinstance(attr_binding.value, AttributeSet)
    assert isinstance(explicit_binding.value, AttributeSet)
    assert attr_binding.nested is True
    assert explicit_binding.nested is False
    assert attr_binding.value.values[0].name == "bar"
    assert explicit_binding.value.values[0].name == "bar"
    assert attr_binding.value.values[0].nested is False
    assert explicit_binding.value.values[0].nested is False
