"""Cover attrpath helper branches for parsing and rebuilding."""

import pytest

from nix_manipulator.cli.manipulations import (
    _parse_npath,
    _remove_attrpath_value,
    _set_attrpath_value,
)
from nix_manipulator.expressions.binding import Binding, _split_attrpath
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.set import (
    AttributeSet,
    _expand_attrpath_binding,
    _merge_attrpath_bindings,
)
from nix_manipulator.parser import parse


def test_split_attrpath_handles_escapes():
    segments = _split_attrpath('"foo\\"bar".baz')
    assert segments == ['"foo\\"bar"', "baz"]
    assert _split_attrpath('foo."bar.baz"') == ["foo", '"bar.baz"']


def test_split_attrpath_handles_interpolation():
    segments = _split_attrpath("foo.${toString ../meta-maintainers.nix}.bar")
    assert segments == [
        "foo",
        "${toString ../meta-maintainers.nix}",
        "bar",
    ]


def test_split_attrpath_interpolation_with_quotes_and_braces():
    segments = _split_attrpath('foo.${"a\\"b"}.bar')
    assert segments == ["foo", '${"a\\"b"}', "bar"]
    assert _split_attrpath("foo.${{}}.bar") == ["foo", "${{}}", "bar"]


def test_split_attrpath_interpolation_inside_quotes():
    segments = _split_attrpath('foo."bar${baz}".qux')
    assert segments == ["foo", '"bar${baz}"', "qux"]


@pytest.mark.parametrize(
    "text",
    [
        "foo..bar",
        "foo.",
        '"foo',
    ],
)
def test_split_attrpath_errors(text: str):
    with pytest.raises(ValueError):
        _split_attrpath(text)


def test_split_attrpath_unterminated_interpolation():
    with pytest.raises(ValueError, match="Unterminated attrpath interpolation"):
        _split_attrpath("foo.${bar")


def test_parse_npath_escape_sequences():
    segments = _parse_npath('foo."bar\\n\\r\\t\\"\\\\\\x"')
    assert segments[0].name == "foo"
    assert segments[1].quoted is True
    assert "\n" in segments[1].name


@pytest.mark.parametrize(
    "npath, match",
    [
        ("", "cannot be empty"),
        ("foo..bar", "empty segment"),
        ("foo.bar$", "valid identifier"),
        ('foo"bar"', "segment boundary"),
        ('foo."bar', "unterminated"),
        ('foo."bar\\', "dangling escape"),
    ],
)
def test_parse_npath_errors(npath: str, match: str):
    with pytest.raises(ValueError, match=match):
        _parse_npath(npath)


def test_parse_duplicate_attrpath_binding_raises():
    with pytest.raises(ValueError, match="Duplicate attrpath binding"):
        parse("{ a.b = 1; a.b = 2; }")


def test_merge_attrpath_bindings_rejects_invalid_root():
    bad = Binding(name="a", value=1, nested=True)
    with pytest.raises(ValueError, match="Invalid attrpath binding"):
        _merge_attrpath_bindings([bad, bad])


def test_merge_attrpath_bindings_keeps_explicit_duplicates():
    first = Binding(name="a", value=1)
    second = Binding(name="a", value=2)
    merged = _merge_attrpath_bindings([first, second])
    assert merged == [first, second]


def test_expand_attrpath_binding_errors():
    root = Binding(name="a", value=1, nested=True)
    with pytest.raises(ValueError, match="attrset"):
        _expand_attrpath_binding(root)

    leaf = Binding(name="b", value=1, nested=True)
    root = Binding(
        name="a",
        value=AttributeSet(values=[leaf]),
        nested=True,
    )
    with pytest.raises(ValueError, match="attrset"):
        _expand_attrpath_binding(root)

    root = Binding(
        name="a",
        value=AttributeSet(values=[Inherit(names=[Identifier(name="x")])]),
        nested=True,
    )
    with pytest.raises(ValueError, match="non-binding"):
        _expand_attrpath_binding(root)


def test_attrpath_rebuild_falls_back_on_mismatch():
    leaf = Binding(name="b", value=1, nested=True)
    root = Binding(
        name="a",
        value=AttributeSet(values=[leaf]),
        nested=True,
    )
    rebuilt = AttributeSet(values=[root], multiline=False).rebuild()
    assert "a = {" in rebuilt
    assert "a.b" not in rebuilt


def test_set_attrpath_value_errors_and_adds_leaf():
    value_expr = Identifier(name="x")
    root = Binding(
        name="a",
        value=AttributeSet(values=[]),
        nested=True,
    )
    _set_attrpath_value(AttributeSet(values=[root]), root, ["a", "b"], value_expr)
    assert root.value.values[0].name == "b"
    assert root.value.values[0].nested is False

    bad_root = Binding(name="a", value=1, nested=True)
    with pytest.raises(ValueError, match="Attrpath root"):
        _set_attrpath_value(
            AttributeSet(values=[bad_root]), bad_root, ["a", "b"], value_expr
        )

    root = Binding(
        name="a",
        value=AttributeSet(values=[Binding(name="b", value=1, nested=True)]),
        nested=True,
    )
    with pytest.raises(ValueError, match="attribute set"):
        _set_attrpath_value(
            AttributeSet(values=[root]), root, ["a", "b", "c"], value_expr
        )

    root = Binding(
        name="a",
        value=AttributeSet(values=[Binding(name="b", value=1)]),
        nested=True,
    )
    with pytest.raises(ValueError, match="Mixed explicit"):
        _set_attrpath_value(
            AttributeSet(values=[root]), root, ["a", "b", "c"], value_expr
        )

    root = Binding(
        name="a",
        value=AttributeSet(
            values=[Binding(name="b", value=AttributeSet(values=[]), nested=True)]
        ),
        nested=True,
    )
    with pytest.raises(ValueError, match="Mixed explicit"):
        _set_attrpath_value(AttributeSet(values=[root]), root, ["a", "b"], value_expr)


def test_remove_attrpath_value_errors_and_prunes():
    with pytest.raises(KeyError):
        _remove_attrpath_value(AttributeSet(values=[]), ["a", "b"])

    leaf = Binding(name="b", value=Identifier(name="x"))
    root = Binding(
        name="a",
        value=AttributeSet(values=[leaf]),
        nested=True,
    )
    target = AttributeSet(values=[root])
    _remove_attrpath_value(target, ["a", "b"])
    assert target.values == []

    leaf = Binding(name="b", value=AttributeSet(values=[]), nested=True)
    root = Binding(
        name="a",
        value=AttributeSet(values=[leaf]),
        nested=True,
    )
    with pytest.raises(KeyError):
        _remove_attrpath_value(AttributeSet(values=[root]), ["a", "b"])

    leaf = Binding(name="b", value=1, nested=True)
    root = Binding(
        name="a",
        value=AttributeSet(values=[leaf]),
        nested=True,
    )
    with pytest.raises(ValueError, match="attribute set"):
        _remove_attrpath_value(AttributeSet(values=[root]), ["a", "b", "c"])
