from nix_manipulator.expressions.list import NixList
from nix_manipulator.parser import parse


def test_nix_list_is_subscriptable():
    """List expressions should allow list-style indexing."""
    source = parse('{ patches = [ 1 "two" true null ]; }')
    patches = source.expr["patches"]

    assert isinstance(patches, NixList)
    first = patches[0]
    second = patches[1]
    third = patches[2]
    fourth = patches[3]

    assert first.value == 1
    assert second.value == "two"
    assert third.value is True
    assert fourth.value is None


def test_nix_list_supports_slicing_and_negative_indexing():
    """List expressions should behave like Python lists for slicing and indices."""
    source = parse('{ patches = [ 1 "two" 3 ]; }')
    patches = source.expr["patches"]

    assert patches[-1].value == 3
    sliced = patches[0:2]
    assert [item.value for item in sliced] == [1, "two"]
