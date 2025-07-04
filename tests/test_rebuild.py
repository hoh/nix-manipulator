from nix_manipulator.symbols import (
    Comment,
    FunctionCall,
    FunctionDefinition,
    NixAttributeSet,
    NixBinding,
    NixIdentifier,
    NixList,
    NixWith,
    Primitive,
    empty_line,
)


def test_rebuild_nix_identifier():
    assert NixIdentifier(name="foo").rebuild() == "foo"
    assert NixIdentifier(name="foo-bar").rebuild() == "foo-bar"
    assert NixIdentifier(name="foo.bar").rebuild() == "foo.bar"
    assert (
        NixIdentifier(
            name="accelerate",
            before=[
                empty_line,
                Comment(text="dependencies"),
            ],
        ).rebuild()
        == "\n# dependencies\naccelerate"
    )


def test_rebuild_nix_list_single_line():
    assert (
        NixList(
            value=[
                NixIdentifier(name="foo"),
                NixIdentifier(name="bar"),
            ],
            multiline=False,
        ).rebuild()
        == "[ foo bar ]"
    )


def test_rebuild_nix_list_multiline():
    assert (
        NixList(
            value=[
                NixIdentifier(name="foo"),
                NixIdentifier(name="bar"),
            ],
            multiline=True,
        ).rebuild()
        == "[\n  foo\n  bar\n]"
    )


def test_rebuild_nix_list_multiline_not_specified():
    # Multiline is the default
    assert (
        NixList(
            value=[
                NixIdentifier(name="foo"),
                NixIdentifier(name="bar"),
            ]
        ).rebuild()
        == "[\n  foo\n  bar\n]"
    )


def test_nix_with():
    assert (
        NixWith(
            environment=NixIdentifier(name="lib.maintainers"),
            body=NixList(value=[NixIdentifier(name="hoh")], multiline=False),
        ).rebuild()
        == "with lib.maintainers; [ hoh ]"
    )


def test_nix_with_multiple_attributes():
    assert (
        NixWith(
            environment=NixIdentifier(name="lib.maintainers"),
            body=NixList(value=[NixIdentifier(name="hoh"), NixIdentifier(name="mic92")],
                         multiline=False),
        ).rebuild()
        == "with lib.maintainers; [ hoh mic92 ]"
    )


def test_nix_binding():
    assert (
        NixBinding(
            name="foo",
            value=NixIdentifier(name="bar"),
        ).rebuild()
        == "foo = bar;"
    )

    assert (
        NixBinding(
            name="foo",
            value=NixList(
                value=[
                    NixIdentifier(name="bar"),
                    NixIdentifier(name="baz"),
                ],
                multiline=False,
            ),
        ).rebuild()
        == "foo = [ bar baz ];"
    )


def test_nix_comment():
    assert Comment(text="foo").rebuild() == "# foo"
    assert Comment(text="foo\nbar").rebuild() == "# foo\n# bar"
    assert (
        Primitive(
            value=True,
            before=[
                Comment(text="Many tests require internet access."),
                empty_line,
            ],
        ).rebuild()
        == "# Many tests require internet access.\n\ntrue"
    )

    assert (
        NixBinding(
            name="alice", value="bob", before=[Comment(text="This is a comment")]
        ).rebuild()
        == '# This is a comment\nalice = "bob";'
    )


def test_nix_expression():
    assert Primitive(value=True, before=[]).rebuild() == "true"


def test_nix_set():
    assert (
        NixAttributeSet.from_dict(
            {
                "foo": NixIdentifier(name="bar"),
                "baz": NixList(
                    value=[
                        NixIdentifier(name="qux"),
                        NixIdentifier(name="quux"),
                    ],
                    multiline=False,
                ),
            }
        ).rebuild()
        == "{\n  foo = bar;\n  baz = [ qux quux ];\n}"
    )


def test_nix_function_definition_empty_set():
    # Empty sets as input and output
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[],
            output=NixAttributeSet(values=[]),
        ).rebuild()
        == "{ }: { }"
    )


def test_nix_function_definition_one_binding():
    assert (
        FunctionDefinition(
            argument_set=[NixIdentifier(name="pkgs")],
            let_statements=[],
            output=NixAttributeSet.from_dict({"pkgs": NixIdentifier(name="pkgs")}),
        ).rebuild()
        == "{\n  pkgs,\n}:\n{\n  pkgs = pkgs;\n}"
    )


def test_nix_function_definition_let_bindings():
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding(name="foo", value=NixIdentifier(name="bar")),
                NixBinding(name="alice", value="bob"),
            ],
            output=NixAttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings():
    # Let statement with comments
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding(name="foo", value=NixIdentifier(name="bar")),
                NixBinding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
            output=NixAttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_let_statements_with_comment():
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                NixBinding(name="foo", value=NixIdentifier(name="bar")),
                NixBinding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
            output=NixAttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings_complex():
    assert (
        FunctionDefinition(
            argument_set=[NixIdentifier(name="pkgs")],
            let_statements=[
                NixBinding(name="pkgs-copy", value=NixIdentifier(name="pkgs")),
                NixBinding(name="alice", value="bob"),
            ],
            output=NixAttributeSet.from_dict(
                {"pkgs-again": NixIdentifier(name="pkgs-copy")}
            ),
        ).rebuild()
        == '{\n  pkgs,\n}:\nlet\n  pkgs-copy = pkgs;\n  alice = "bob";\nin\n{\n  pkgs-again = pkgs-copy;\n}'
    )


def test_function_call():
    assert (
        FunctionCall(
            name="foo",
            argument=NixAttributeSet.from_dict(
                {"foo": NixIdentifier(name="bar"), "alice": "bob"}
            ),
        ).rebuild()
        == 'foo {\n  foo = bar;\n  alice = "bob";\n}'
    )


def test_function_with_comments():
    assert (
        FunctionCall(
            name="foo",
            argument=NixAttributeSet(
                values=[
                    NixBinding(
                        name="foo",
                        value=NixIdentifier(name="bar"),
                        before=[Comment(text="This is a comment")],
                    ),
                    NixBinding(name="alice", value="bob"),
                ]
            ),
        ).rebuild()
        == 'foo {\n  # This is a comment\n  foo = bar;\n  alice = "bob";\n}'
    )


def test_function_definition_with_function_call():
    assert (
        FunctionDefinition(
            argument_set=[NixIdentifier(name="pkgs")],
            output=FunctionCall(
                name="buildPythonPackage",
                recursive=True,
                argument=NixAttributeSet.from_dict(
                    {"pkgs": NixIdentifier(name="pkgs"), "alice": "bob"}
                ),
            ),
        ).rebuild()
        == """{\n  pkgs,\n}:\nbuildPythonPackage rec {\n  pkgs = pkgs;\n  alice = "bob";\n}"""
    )


def test_function_call_recursive():
    assert (
        FunctionCall(
            name="foo",
            recursive=True,
            argument=NixAttributeSet.from_dict(
                values={
                    "foo": NixIdentifier(name="bar"),
                    "alice": "bob",
                }
            ),
        ).rebuild()
        == 'foo rec {\n  foo = bar;\n  alice = "bob";\n}'
    )


expected_list = """
[
  setuptools
  setuptools-scm
]
""".strip("\n")


def test_list():
    assert (
        NixList(
            value=[
                NixIdentifier(name="setuptools"),
                NixIdentifier(name="setuptools-scm"),
            ],
        ).rebuild()
        == expected_list
    )


expected_binding_list = """
build-system = [
  setuptools
  setuptools-scm
];
""".strip("\n")


def test_binding_list():
    assert (
        NixBinding(
            name="build-system",
            value=NixList(
                value=[
                    NixIdentifier(name="setuptools"),
                    NixIdentifier(name="setuptools-scm"),
                ],
            ),
        ).rebuild()
        == expected_binding_list
    )


def test_indented_function_call():
    assert (
        NixList(
            value=[
                FunctionCall(name="fetchFromGitHub"),
            ],
        ).rebuild()
        == "[\n  fetchFromGitHub\n]"
    )

    assert (
        NixList(
            value=[
                FunctionCall(
                    name="fetchFromGitHub",
                    argument=NixAttributeSet(
                        values=[
                            NixBinding(
                                name="owner",
                                value="huggingface",
                            ),
                            NixBinding(
                                name="repo",
                                value="trl",
                            ),
                        ]
                    ),
                ),
            ],
        ).rebuild()
        == '[\n  fetchFromGitHub {\n    owner = "huggingface";\n    repo = "trl";\n  }\n]'
    )
