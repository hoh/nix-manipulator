"""Test operator overloading."""

from textwrap import dedent

import pytest

from nix_manipulator.expressions import AttributeSet, Binding, Identifier
from nix_manipulator.parser import parse


def test_get_values():
    """Ensure the API allows getting values and comparing them easily"""
    source = parse("""
{
  a = 1;
  b = "test";
  c = null;
  d = {
    e = 2;
  };
}
""")
    assert source["a"] == 1
    assert source["b"] == "test"
    assert source["c"] == None  # noqa: E711
    assert source["c"].value is None
    assert source["d"]["e"] == 2


def test_modify_values():
    """Ensure the API allows modifying attribute values"""
    source = parse("""
    {
      a = 1;
      b = "test";
      c = {
        d = 2;
      };
    }
    """)
    source["a"] += 1
    assert source["a"] == 2
    source["b"] += "test"
    assert source["b"] == "testtest"
    source["c"]["d"] += 1
    source["c"]["e"] = 3
    assert source["c"]["d"] == 3
    assert source["c"]["e"] == 3


def test_set_add_value():
    """Ensure set_value correctly updates attribute values."""
    source = parse("{ foo = 1; }")
    assert source["foo"] == 1
    source["bar"] = 2
    assert source["bar"] == 2
    assert source.rebuild() == "{ foo = 1; bar = 2; }"


def test_set_remove_value():
    """Ensure set_value correctly updates attribute values."""
    source = parse("{ foo = 1; }")
    del source["foo"]
    assert source.rebuild() == "{ }"


def test_set_update_value():
    """Ensure set_value correctly updates attribute values."""
    source = parse("{ foo = 1; }")
    source["foo"] = 2
    assert source.rebuild() == "{ foo = 2; }"


def test_set_update_recursive():
    """Ensure set_value correctly updates attribute values."""
    source = parse("{ foo = { bar = 1; }; }")
    source["foo"]["bar"] = 2
    assert source.rebuild() == "{ foo = { bar = 2; }; }"


def test_set_update_value_dict_coerces_attrset():
    """Ensure dict updates are coerced into attribute sets."""
    source = parse("{ foo = 1; }")
    source["foo"] = {"bar": 2}
    assert source.rebuild() == "{ foo = { bar = 2; }; }"


def test_set_remove_missing_value():
    """Ensure set_value correctly updates attribute values."""
    source = parse("{ foo = 1; }")
    with pytest.raises(KeyError):
        del source["bar"]


def test_scope_update():
    """Ensure set_value correctly updates attribute values."""
    source = AttributeSet({"foo": 1}, scope=[Binding(name="bar", value=2)])
    assert source["foo"] == 1
    source.scope["bar"] = 3
    assert source.rebuild() == "let\n  bar = 3;\nin\n{ foo = 1; }"


def test_scope_update_dict_coerces_attrset():
    """Ensure scope updates coerce dict payloads."""
    source = AttributeSet({"foo": 1}, scope=[Binding(name="bar", value=2)])
    source.scope["bar"] = {"baz": 4}
    assert source.rebuild() == "let\n  bar = { baz = 4; };\nin\n{ foo = 1; }"


def test_with_scope():
    """Ensure the API allows getting values and comparing them easily"""
    source = parse("""
let
  a = 1;
  b = "test";
in
{
  c = a;
  d = b;
}
""")
    expr = source.expr
    assert expr.scope["a"] == 1
    assert expr.scope["b"] == "test"
    assert expr["c"] == Identifier("a")
    assert expr["d"] == Identifier("b")


def test_top_level_with_operator_access():
    """Operator access should work when the top level is a with wrapper."""
    source = parse("""
with { a = 1; };
{
  foo = a;
}
""")
    assert source["foo"] == Identifier("a")
    source["foo"] = 2
    assert source.rebuild() == "with { a = 1; };\n{\n  foo = 2;\n}"


def test_top_level_with_identifier_operator_access():
    """Operator access should resolve through with-body identifiers."""
    source = parse(
        dedent(
            """\
            with { body = { foo = 1; }; };
            body
            """
        )
    )
    assert source["foo"] == 1
    source["foo"] = 3
    assert source.rebuild() == "with { body = { foo = 3; }; };\nbody\n"


def test_operator_identifier_requires_value_resolution():
    """Operator access keeps identifier indirection without overriding it."""
    source = parse(
        """
        rec {
          version = package_version;
          package_version = "1.0.0";
        }
        """
    )
    version = source["version"]
    assert isinstance(version, Identifier)
    assert version.name == "package_version"
    resolved = version.value
    assert getattr(resolved, "value", None) == "1.0.0"
