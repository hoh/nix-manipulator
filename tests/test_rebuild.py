from nix_manipulator import NixIdentifier, NixList, NixSet, NixWith, NixBinding, NixExpression, Comment, empty_line, FunctionCall, FunctionDefinition


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


def test_nix_expression():
    assert NixExpression(
        value=True,
        before=[]
    ).rebuild() == "true"


def test_nix_set():
    assert NixSet({
        'foo': NixIdentifier('bar'),
        'baz': NixList([
            NixIdentifier('qux'),
            NixIdentifier('quux'),
        ], multiline=False),
    }).rebuild() == "{\n  foo = bar;\n  baz = [ qux quux ];\n}"


def test_nix_function_definition():
    # Empty sets as input and output
    assert FunctionDefinition(
        argument_set=[],
        let_statements=[],
        result=NixSet({}),
    ).rebuild() == "{ }: { }"

    assert FunctionDefinition(
        argument_set=[NixIdentifier("pkgs")],
        let_statements=[],
        result=NixSet({"pkgs": NixIdentifier("pkgs")}),
    ).rebuild() == "{\n  pkgs\n}:\n{\n  pkgs = pkgs;\n}"

    assert FunctionDefinition(
        argument_set=[],
        let_statements=[
            NixBinding("foo", NixIdentifier("bar")),
            NixBinding("alice", "bob"),
        ],
        result=NixSet({}),
    ).rebuild() == "{ }:\nlet\n  foo = bar;\n  alice = \"bob\";\nin\n{ }"

    assert FunctionDefinition(
        argument_set=[NixIdentifier("pkgs")],
        let_statements=[
            NixBinding("pkgs-copy", NixIdentifier("pkgs")),
            NixBinding("alice", "bob"),
        ],
        result=NixSet({"pkgs-again": NixIdentifier("pkgs-copy")}),
    ).rebuild() == "{\n  pkgs\n}:\nlet\n  pkgs-copy = pkgs;\n  alice = \"bob\";\nin\n{\n  pkgs-again = pkgs-copy;\n}"

def test_function_call():
    assert FunctionCall(
        name="foo",
        arguments=[
            NixBinding("foo", NixIdentifier("bar")),
            NixBinding("alice", "bob"),
        ],
    ).rebuild() == "foo {\n  foo = bar;\n  alice = \"bob\";\n}"
