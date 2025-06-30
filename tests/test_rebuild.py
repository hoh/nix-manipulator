from nix_manipulator import NixIdentifier, NixList, NixSet, NixWith, NixBinding, NixExpression, Comment, empty_line


def test_rebuild_nix_identifier():
    assert NixIdentifier('foo').rebuild() == "foo"
    assert NixIdentifier('foo-bar').rebuild() == "foo-bar"
    assert NixIdentifier('foo.bar').rebuild() == "foo.bar"


def test_rebuild_nix_list():
    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ], multiline=False).rebuild() == "[ foo bar ]"

    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ], multiline=True).rebuild() == "[\n  foo\n  bar\n]"

    # Multiline is the default
    assert NixList([
        NixIdentifier('foo'),
        NixIdentifier('bar'),
    ]).rebuild() == "[\n  foo\n  bar\n]"


def test_nix_with():
    assert NixWith(
        expression=NixIdentifier('lib.maintainers'),
        attributes=[NixIdentifier('hoh')],
    ).rebuild() == "with lib.maintainers; [ hoh ];"

    assert NixWith(
        expression=NixIdentifier('lib.maintainers'),
        attributes=[
            NixIdentifier('hoh'),
            NixIdentifier('mic92'),
        ],
    ).rebuild() == "with lib.maintainers; [ hoh mic92 ];"


def test_nix_binding():
    assert NixBinding(
        name='foo',
        value=NixIdentifier('bar'),
    ).rebuild() == "foo = bar;"

    assert NixBinding(
        name='foo',
        value=NixList([
            NixIdentifier('bar'),
            NixIdentifier('baz'),
        ], multiline=False),
    ).rebuild() == "foo = [ bar baz ];"

def test_nix_comment():
    assert Comment(text='foo').rebuild() == "# foo"
    assert Comment(text='foo\nbar').rebuild() == "# foo\n# bar"
    assert NixExpression(
        value=True,
        before=[
            Comment(text="Many tests require internet access."),
            empty_line,
        ],
    ).rebuild() == "# Many tests require internet access.\n\ntrue"