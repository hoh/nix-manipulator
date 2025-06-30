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