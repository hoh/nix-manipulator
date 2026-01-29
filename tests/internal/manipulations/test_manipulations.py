"""Validate manipulation error paths to guard CLI and API behavior."""

from textwrap import dedent

import pytest

from nix_manipulator.cli.manipulations import remove_value, set_value
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.parser import parse, parse_to_ast


def test_set_value_empty_value_raises():
    """Ensure empty values are rejected so CLI edits are explicit and safe."""
    source = parse("{ foo = 1; }")
    with pytest.raises(ValueError, match="Provided value contains no expressions"):
        set_value(source, "foo", "")


def test_set_value_invalid_value_raises():
    """Reject invalid values so edits never inject malformed Nix."""
    source = parse("{ foo = 1; }")
    with pytest.raises(
        ValueError, match="Provided value must contain exactly one valid expression"
    ):
        set_value(source, "foo", "{ a = 1; } }")


def test_set_value_multiple_expressions_source_raises():
    """Reject non-attrset top-level inputs so CLI edits remain predictable."""
    source = parse("{ foo = 1; }\n{ bar = 2; }")
    with pytest.raises(
        ValueError,
        match="Top-level expression must be an attribute set or function definition",
    ):
        set_value(source, "foo", "2")


def test_remove_value_missing_key_raises():
    """Confirm missing-key deletes raise to avoid silently masking typos."""
    source = parse("{ foo = 1; }")
    with pytest.raises(KeyError):
        remove_value(source, "bar")


def test_remove_value_empty_source_raises():
    """Reject edits against empty inputs to surface user mistakes early."""
    source = parse("")
    with pytest.raises(ValueError, match="Source contains no expressions"):
        remove_value(source, "foo")


def test_remove_value_multiple_expressions_raises():
    """Reject non-attrset top-level inputs so CLI edits are unambiguous."""
    source = parse("{ foo = 1; }\n{ bar = 2; }")
    with pytest.raises(
        ValueError,
        match="Top-level expression must be an attribute set or function definition",
    ):
        remove_value(source, "foo")


def test_let_expression_delete_missing_key_raises():
    """Match AttributeSet behavior so deletion errors are consistent."""
    root = parse_to_ast("let foo = 1; in foo")
    let_node = next(child for child in root.children if child.type == "let_expression")
    let_expr = LetExpression.from_cst(let_node)
    with pytest.raises(KeyError):
        del let_expr["bar"]


def test_set_value_nested_path_updates():
    """Ensure NPath traversal updates nested attribute sets."""
    source = parse("{ foo = { bar = 1; }; }")
    assert set_value(source, "foo.bar", "2") == "{ foo = { bar = 2; }; }"


def test_set_value_nested_path_creates_missing_sets():
    """Create intermediate attrsets when NPath segments are missing."""
    source = parse("{ }")
    assert set_value(source, "foo.bar", "1") == "{ foo = { bar = 1; }; }"


def test_set_value_nested_path_rejects_non_attrset():
    """Reject NPath traversal into non-attrset values."""
    source = parse("{ foo = 1; }")
    with pytest.raises(ValueError, match="does not point to an attribute set"):
        set_value(source, "foo.bar", "2")


def test_set_value_prefers_direct_attrpath_match():
    """Prefer direct attrpath bindings over implicit nesting."""
    source = parse("{ foo.bar = 1; }")
    assert set_value(source, "foo.bar", "2") == "{ foo.bar = 2; }"


def test_set_value_prefers_explicit_leaf():
    """Prefer explicit attrpath leaves when nested branches also exist."""
    source = parse("{ a.b.c = 1; a.b = { d = 2; }; }")
    assert set_value(source, "a.b", "{ d = 3; }") == "{ a.b.c = 1; a.b = { d = 3; }; }"


def test_set_value_attrpath_adds_leaf():
    """Maintain attrpath style when extending existing attrpath roots."""
    source = parse("{ foo.bar = 1; }")
    assert set_value(source, "foo.baz", "2") == "{ foo.bar = 1; foo.baz = 2; }"


def test_set_value_attrpath_root_rejects_overwrite():
    """Reject overwriting an attrpath root with a direct binding."""
    source = parse("{ foo.bar = 1; }")
    with pytest.raises(ValueError, match="attrpath-derived"):
        set_value(source, "foo", "2")


def test_set_value_resolves_identifier_body():
    """set_value should follow identifier references to the target attrset."""
    source = parse(
        dedent(
            """\
            with { body = { foo = 1; }; };
            body
            """
        )
    )
    updated = set_value(source, "foo", "2")
    assert updated.rstrip("\n") == "with { body = { foo = 2; }; };\nbody"


def test_set_scope_path_updates_existing_attrset_body():
    """set_value should not create a scope when editing an existing attrset body."""
    source = parse(
        dedent(
            """\
            with { body = { foo = 1; }; };
            body
            """
        )
    )
    updated = set_value(source, "@foo", "2")
    assert updated.rstrip("\n") == "with { body = { foo = 2; }; };\nbody"


def test_remove_value_nested_path_deletes_binding():
    """Delete nested attrpath bindings via NPath traversal."""
    source = parse("{ foo = { bar = 1; baz = 2; }; }")
    assert remove_value(source, "foo.bar") == "{ foo = { baz = 2; }; }"


def test_remove_value_attrpath_leaf_prunes_empty_root():
    """Drop the attrpath root when the last leaf is removed."""
    source = parse("{ foo.bar = 1; }")
    assert remove_value(source, "foo.bar") == "{ }"


def test_remove_value_attrpath_root_raises():
    """Reject deleting an attrpath root without a concrete leaf."""
    source = parse("{ foo.bar = 1; }")
    with pytest.raises(KeyError):
        remove_value(source, "foo")


def test_remove_value_prefers_explicit_leaf():
    """Prefer explicit leaves when a nested attrpath branch also exists."""
    source = parse("{ a.b.c = 1; a.b = { d = 2; }; }")
    assert remove_value(source, "a.b") == "{ a.b.c = 1; }"


def test_remove_value_nested_path_rejects_non_attrset():
    """Reject NPath traversal into non-attrset values during delete."""
    source = parse("{ foo = 1; }")
    with pytest.raises(ValueError, match="does not point to an attribute set"):
        remove_value(source, "foo.bar")


def test_remove_value_attrpath_missing_leaf_raises():
    """Raise when removing a missing attrpath leaf beneath an existing root."""
    source = parse("{ foo.bar = 1; }")
    with pytest.raises(KeyError):
        remove_value(source, "foo.baz")


def test_set_scope_auto_creates_layer():
    """Auto-create a single scope when addressing the innermost layer."""
    source = parse("{ foo = 1; }")
    assert set_value(source, "@bar", "2") == "let\n  bar = 2;\nin\n{ foo = 1; }"


def test_scope_set_rm_round_trip_preserves_trivia():
    """Adding then removing a scope should keep leading/trailing trivia."""
    original = "# heading\n\n{ foo = 1; }\n\n# footer\n"
    with_bar = set_value(parse(original), "@bar", "2")
    round_trip = remove_value(parse(with_bar), "@bar")
    assert round_trip == original.rstrip("\n")


def test_set_scope_nested_layers():
    """Select innermost and outer scopes with @ depth."""
    source = parse(
        """\
let
  a = 1;
in
  let
    b = 2;
  in
    {
      c = a + b;
    }
"""
    )
    assert (
        set_value(source, "@b", "20")
        == """\
let
  a = 1;
in
let
  b = 20;
in
{
  c = a + b;
}
"""
    )

    source = parse(
        """\
let
  a = 1;
in
  let
    b = 2;
  in
    {
      c = a + b;
    }
"""
    )
    assert (
        set_value(source, "@@a", "10")
        == """\
let
  a = 10;
in
let
  b = 2;
in
{
  c = a + b;
}
"""
    )


def test_set_scope_too_deep_errors():
    """Reject edits when requested scope depth is missing."""
    source = parse(
        """\
let
  a = 1;
in
  let
    b = 2;
  in
    {
      c = a + b;
    }
"""
    )
    with pytest.raises(ValueError, match="scope layer does not exist"):
        set_value(source, "@@@x", "1")


def test_remove_scope_prunes_empty_layer():
    """Remove an empty scope layer after deleting its last binding."""
    source = parse(
        """\
let
  b = 2;
in
  {
    c = b;
  }
"""
    )
    assert (
        remove_value(source, "@b")
        == """\
{
  c = b;
}
"""
    )


def test_remove_scope_nested_layer():
    """Unwrap a nested scope when its bindings are removed."""
    source = parse(
        """\
let
  a = 1;
in
  let
    b = 2;
  in
    {
      c = a + b;
    }
"""
    )
    assert (
        remove_value(source, "@b")
        == """\
let
  a = 1;
in
{
  c = a + b;
}
"""
    )


def test_npath_quoted_segment_updates():
    """Allow quoted segments to target names with dots."""
    source = parse('{ foo = { "bar.baz" = 1; }; }')
    assert set_value(source, 'foo."bar.baz"', "2") == '{ foo = { "bar.baz" = 2; }; }'


def test_set_value_empty_npath_raises():
    """Reject empty NPaths so edits must name a binding."""
    source = parse("{ }")
    with pytest.raises(ValueError, match="NPath cannot be empty"):
        set_value(source, "", "1")


def test_scope_path_requires_binding_name():
    """Scope selectors must include a binding name."""
    source = parse("{ }")
    with pytest.raises(ValueError, match="Scope path is missing a binding name"):
        set_value(source, "@", "1")


def test_scope_attrpath_root_rejects_overwrite():
    """Respect attrpath roots inside scopes when setting values."""
    source = parse(
        """\
let
  foo.bar = 1;
in
  { }
"""
    )
    with pytest.raises(ValueError, match="attrpath-derived"):
        set_value(source, "@foo", "2")


def test_scope_attrpath_root_delete_raises():
    """Reject deleting attrpath roots inside scopes."""
    source = parse(
        """\
let
  foo.bar = 1;
in
  { }
"""
    )
    with pytest.raises(KeyError):
        remove_value(source, "@foo")


def test_remove_scope_missing_layer_raises():
    """Error on scope depth that does not exist."""
    source = parse("{ }")
    with pytest.raises(ValueError, match="scope layer does not exist"):
        remove_value(source, "@@foo")


def test_scope_nested_path_updates_binding():
    """Allow nested path edits inside a scope layer."""
    source = parse(
        """\
let
  foo = { };
in
  { }
"""
    )
    assert (
        set_value(source, "@foo.bar", "1")
        == """\
let
  foo = { bar = 1; };
in
{ }
"""
    )


def test_scope_nested_path_delete_binding():
    """Delete nested bindings inside a scope layer."""
    source = parse(
        """\
let
  foo = { bar = 1; };
in
  { }
"""
    )
    assert (
        remove_value(source, "@foo.bar")
        == """\
let
  foo = { };
in
{ }
"""
    )


def test_scope_attrpath_extend_existing_root():
    """Extend an attrpath binding inside a scope layer."""
    source = parse(
        """\
let
  foo.bar = 1;
in
  { }
"""
    )
    assert (
        set_value(source, "@foo.baz", "2")
        == """\
let
  foo.bar = 1;
  foo.baz = 2;
in
{ }
"""
    )


def test_scope_attrpath_update_existing_leaf():
    """Update an existing attrpath leaf inside a scope layer."""
    source = parse(
        """\
let
  foo.bar = 1;
in
  { }
"""
    )
    assert (
        set_value(source, "@foo.bar", "3")
        == """\
let
  foo.bar = 3;
in
{ }
"""
    )


def test_scope_attrpath_remove_leaf_prunes_scope():
    """Remove an attrpath leaf inside a scope layer."""
    source = parse(
        """\
let
  foo.bar = 1;
in
  { }
"""
    )
    assert remove_value(source, "@foo.bar") == "{ }\n"


def test_set_value_adds_new_top_level_binding():
    """Add a top-level binding when it is missing."""
    source = parse("{ }")
    assert set_value(source, "foo", "1") == "{ foo = 1; }"


def test_set_value_requires_quotes_for_hyphenated_identifier():
    """Hyphenated attribute names must be quoted to avoid invalid Nix."""
    source = parse("{ }")
    with pytest.raises(ValueError, match="valid identifier"):
        set_value(source, "foo-bar", "1")


def test_set_value_accepts_quoted_hyphenated_identifier():
    """Quoted hyphenated names round-trip with quoting preserved."""
    source = parse("{ }")
    assert set_value(source, '"foo-bar"', "1") == '{ "foo-bar" = 1; }'


def test_set_value_escapes_interpolation_in_quoted_npath():
    """Quoted NPaths with ${...} should stay literal and avoid interpolation."""
    source = parse("{ foo = { }; }")
    assert set_value(source, 'foo."${bar}"', "1") == '{ foo = { "\\${bar}" = 1; }; }'


def test_set_value_handles_recursive_attrset():
    """Allow edits against top-level recursive attribute sets."""
    source = parse("rec { foo = 1; }")
    assert set_value(source, "foo", "2") == "rec { foo = 2; }"
