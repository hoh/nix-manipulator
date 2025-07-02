from nix_manipulator import (
    NixIdentifier,
    NixList,
    NixSet,
    NixWith,
    NixBinding,
    NixExpression,
    Comment,
    empty_line,
    FunctionCall,
    FunctionDefinition,
)


def test_rebuild_nix_identifier():
    assert NixIdentifier("foo").rebuild() == "foo"
    assert NixIdentifier("foo-bar").rebuild() == "foo-bar"
    assert NixIdentifier("foo.bar").rebuild() == "foo.bar"


def test_rebuild_nix_list_single_line():
    assert (
        NixList(
            [
                NixIdentifier("foo"),
                NixIdentifier("bar"),
            ],
            multiline=False,
        ).rebuild()
        == "[ foo bar ]"
    )

def test_rebuild_nix_list_multiline():
    assert (
        NixList(
            [
                NixIdentifier("foo"),
                NixIdentifier("bar"),
            ],
            multiline=True,
        ).rebuild()
        == "[\n  foo\n  bar\n]"
    )

def test_rebuild_nix_list_multiline_not_specified():
    # Multiline is the default
    assert (
        NixList(
            [
                NixIdentifier("foo"),
                NixIdentifier("bar"),
            ]
        ).rebuild()
        == "[\n  foo\n  bar\n]"
    )

def test_nix_with():
    assert (
        NixWith(
            expression=NixIdentifier("lib.maintainers"),
            attributes=[NixIdentifier("hoh")],
        ).rebuild()
        == "with lib.maintainers; [ hoh ];"
    )

def test_nix_with_multiple_attributes():
    assert (
        NixWith(
            expression=NixIdentifier("lib.maintainers"),
            attributes=[
                NixIdentifier("hoh"),
                NixIdentifier("mic92"),
            ],
        ).rebuild()
        == "with lib.maintainers; [ hoh mic92 ];"
    )


def test_nix_binding():
    assert (
        NixBinding(
            name="foo",
            value=NixIdentifier("bar"),
        ).rebuild()
        == "foo = bar;"
    )

    assert (
        NixBinding(
            name="foo",
            value=NixList(
                [
                    NixIdentifier("bar"),
                    NixIdentifier("baz"),
                ],
                multiline=False,
            ),
        ).rebuild()
        == "foo = [ bar baz ];"
    )


def test_nix_comment():
    assert Comment(text="foo").rebuild() == "# foo\n"
    assert Comment(text="foo\nbar").rebuild() == "# foo\n# bar\n"
    assert (
        NixExpression(
            value=True,
            before=[
                Comment(text="Many tests require internet access."),
                empty_line,
            ],
        ).rebuild()
        == "# Many tests require internet access.\n\ntrue"
    )

    assert (
        NixBinding("alice", "bob", before=[Comment(text="This is a comment")]).rebuild()
        == '# This is a comment\nalice = "bob";'
    )


def test_nix_expression():
    assert NixExpression(value=True, before=[]).rebuild() == "true"


def test_nix_set():
    assert (
        NixSet(
            {
                "foo": NixIdentifier("bar"),
                "baz": NixList(
                    [
                        NixIdentifier("qux"),
                        NixIdentifier("quux"),
                    ],
                    multiline=False,
                ),
            }
        ).rebuild()
        == "{\n  foo = bar;\n  baz = [ qux quux ];\n}"
    )


def test_nix_function_definition():
    # Empty sets as input and output
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[],
            result=NixSet({}),
        ).rebuild()
        == "{ }: { }"
    )

    assert (
        FunctionDefinition(
            argument_set=[NixIdentifier("pkgs")],
            let_statements=[],
            result=NixSet({"pkgs": NixIdentifier("pkgs")}),
        ).rebuild()
        == "{\n  pkgs\n}:\n{\n  pkgs = pkgs;\n}"
    )

    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding("foo", NixIdentifier("bar")),
                NixBinding("alice", "bob"),
            ],
            result=NixSet({}),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    )

    # Let statement with comments
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding("foo", NixIdentifier("bar")),
                NixBinding("alice", "bob", before=[Comment(text="This is a comment")]),
            ],
            result=NixSet({}),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )

    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding("foo", NixIdentifier("bar")),
                NixBinding("alice", "bob", before=[Comment(text="This is a comment")]),
            ],
            result=NixSet({}),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )

    assert (
        FunctionDefinition(
            argument_set=[NixIdentifier("pkgs")],
            let_statements=[
                NixBinding("pkgs-copy", NixIdentifier("pkgs")),
                NixBinding("alice", "bob"),
            ],
            result=NixSet({"pkgs-again": NixIdentifier("pkgs-copy")}),
        ).rebuild()
        == '{\n  pkgs\n}:\nlet\n  pkgs-copy = pkgs;\n  alice = "bob";\nin\n{\n  pkgs-again = pkgs-copy;\n}'
    )


def test_function_call():
    assert (
        FunctionCall(
            name="foo",
            argument=NixSet(values={
                "foo": NixIdentifier("bar"),
                "alice": "bob"
            }),
        ).rebuild()
        == 'foo {\n  foo = bar;\n  alice = "bob";\n}'
    )

def test_function_calls_function_call():
    assert FunctionDefinition(
        argument_set=[NixIdentifier("pkgs")],
        result=FunctionCall(
            name = "buildPythonPackage",
            recursive=True,
            argument=NixSet(values={
                "pkgs": NixIdentifier("pkgs"),
                "alice": "bob"
            }),
        )
    ).rebuild() == """{\n  pkgs\n}:\nbuildPythonPackage rec {\n  pkgs = pkgs;\n  alice = "bob";\n}"""


def test_function_call_recursive():
    assert (
            FunctionCall(
                name="foo",
                recursive=True,
                argument=NixSet(values={
                    "foo": NixIdentifier("bar"),
                    "alice": "bob",
                }),
            ).rebuild()
            == 'foo rec {\n  foo = bar;\n  alice = "bob";\n}'
    )
