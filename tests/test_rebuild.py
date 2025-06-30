from nix_manipulator import NixIdentifier, NixList, NixSet, NixWith, NixBinding, NixExpression


def test_rebuild_nix_identifier():
    assert NixIdentifier('foo').rebuild() == "'foo'"
    assert NixIdentifier('foo-bar').rebuild() == "'foo-bar'"
    assert NixIdentifier('foo.bar').rebuild() == "'foo.bar'"


def test_rebuild_nix_list():
    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ], multiline=False).rebuild() == "[ 'foo' 'bar' ]"

    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ], multiline=True).rebuild() == "[\n  'foo'\n  'bar'\n]"

    # Multiline is the default
    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ]).rebuild() == "[\n  'foo'\n  'bar'\n]"


