from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.with_statement import WithStatement


def test_rebuild_nix_identifier():
    assert Identifier(name="foo").rebuild() == "foo"
    assert Identifier(name="foo-bar").rebuild() == "foo-bar"
    assert Identifier(name="foo.bar").rebuild() == "foo.bar"
    assert (
        Identifier(
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
                Identifier(name="foo"),
                Identifier(name="bar"),
            ],
            multiline=False,
        ).rebuild()
        == "[ foo bar ]"
    )


def test_rebuild_nix_list_multiline():
    assert (
        NixList(
            value=[
                Identifier(name="foo"),
                Identifier(name="bar"),
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
                Identifier(name="foo"),
                Identifier(name="bar"),
            ]
        ).rebuild()
        == "[\n  foo\n  bar\n]"
    )


def test_nix_with():
    assert (
        WithStatement(
            environment=Identifier(name="lib.maintainers"),
            body=NixList(value=[Identifier(name="hoh")], multiline=False),
        ).rebuild()
        == "with lib.maintainers; [ hoh ]"
    )


def test_nix_with_multiple_attributes():
    assert (
        WithStatement(
            environment=Identifier(name="lib.maintainers"),
            body=NixList(
                value=[Identifier(name="hoh"), Identifier(name="mic92")],
                multiline=False,
            ),
        ).rebuild()
        == "with lib.maintainers; [ hoh mic92 ]"
    )


def test_nix_binding():
    assert (
        Binding(
            name="foo",
            value=Identifier(name="bar"),
        ).rebuild()
        == "foo = bar;"
    )

    assert (
        Binding(
            name="foo",
            value=NixList(
                value=[
                    Identifier(name="bar"),
                    Identifier(name="baz"),
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
        Binding(
            name="alice", value="bob", before=[Comment(text="This is a comment")]
        ).rebuild()
        == '# This is a comment\nalice = "bob";'
    )


def test_nix_comment_after_identifier():
    assert (
        Identifier(name="alice", after=[Comment(text="This is a comment")]).rebuild()
        == "alice\n# This is a comment"
    )


def test_nix_comment_before_and_after_identifier():
    assert (
        Identifier(
            name="alice",
            before=[Comment(text="A first comment"), empty_line],
            after=[empty_line, Comment(text="This is a comment")],
        ).rebuild()
        == "# A first comment\n\nalice\n\n# This is a comment"
    )


def test_nix_expression():
    assert Primitive(value=True, before=[]).rebuild() == "true"


def test_nix_set():
    assert (
        AttributeSet.from_dict(
            {
                "foo": Identifier(name="bar"),
                "baz": NixList(
                    value=[
                        Identifier(name="qux"),
                        Identifier(name="quux"),
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
            output=AttributeSet(values=[]),
        ).rebuild()
        == "{ }: { }"
    )


def test_nix_function_definition_one_binding():
    assert (
        FunctionDefinition(
            argument_set=[Identifier(name="pkgs")],
            let_statements=[],
            output=AttributeSet.from_dict({"pkgs": Identifier(name="pkgs")}),
        ).rebuild()
        == "{\n  pkgs,\n}:\n{\n  pkgs = pkgs;\n}"
    )


def test_nix_function_definition_empty_lines_in_argument_set():
    assert (
        FunctionDefinition(
            argument_set=[
                Identifier(name="pkgs", before=[empty_line]),
                Identifier(
                    name="pkgs-2",
                    before=[Comment(text="This is a comment"), empty_line],
                ),
                Identifier(
                    name="pkg-3",
                    before=[
                        empty_line,
                        Comment(text="Another comment"),
                    ],
                    after=[empty_line, Comment(text="A final comment")],
                ),
            ],
            let_statements=[],
            output=AttributeSet.from_dict({"pkgs": Identifier(name="pkgs")}),
        ).rebuild()
        == """
{

  pkgs,
  # This is a comment

  pkgs-2,

  # Another comment
  pkg-3,

  # A final comment
}:
{
  pkgs = pkgs;
}
""".strip("\n")
    )


def test_nix_function_definition_let_bindings():
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(name="alice", value="bob"),
            ],
            output=AttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings():
    # Let statement with comments
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
            output=AttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_let_statements_with_comment():
    assert (
        FunctionDefinition(
            argument_set=[],
            let_statements=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
            output=AttributeSet(values=[]),
        ).rebuild()
        == '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings_complex():
    assert (
        FunctionDefinition(
            argument_set=[Identifier(name="pkgs")],
            let_statements=[
                Binding(name="pkgs-copy", value=Identifier(name="pkgs")),
                Binding(name="alice", value="bob"),
            ],
            output=AttributeSet.from_dict({"pkgs-again": Identifier(name="pkgs-copy")}),
        ).rebuild()
        == '{\n  pkgs,\n}:\nlet\n  pkgs-copy = pkgs;\n  alice = "bob";\nin\n{\n  pkgs-again = pkgs-copy;\n}'
    )


def test_function_call():
    assert (
        FunctionCall(
            name="foo",
            argument=AttributeSet.from_dict(
                {"foo": Identifier(name="bar"), "alice": "bob"}
            ),
        ).rebuild()
        == 'foo {\n  foo = bar;\n  alice = "bob";\n}'
    )


def test_function_with_comments():
    assert (
        FunctionCall(
            name="foo",
            argument=AttributeSet(
                values=[
                    Binding(
                        name="foo",
                        value=Identifier(name="bar"),
                        before=[Comment(text="This is a comment")],
                    ),
                    Binding(name="alice", value="bob"),
                ]
            ),
        ).rebuild()
        == 'foo {\n  # This is a comment\n  foo = bar;\n  alice = "bob";\n}'
    )


def test_function_definition_with_function_call():
    assert (
        FunctionDefinition(
            argument_set=[Identifier(name="pkgs")],
            output=FunctionCall(
                name="buildPythonPackage",
                recursive=True,
                argument=AttributeSet.from_dict(
                    {"pkgs": Identifier(name="pkgs"), "alice": "bob"}
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
            argument=AttributeSet.from_dict(
                values={
                    "foo": Identifier(name="bar"),
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
                Identifier(name="setuptools"),
                Identifier(name="setuptools-scm"),
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
        Binding(
            name="build-system",
            value=NixList(
                value=[
                    Identifier(name="setuptools"),
                    Identifier(name="setuptools-scm"),
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
                    argument=AttributeSet(
                        values=[
                            Binding(
                                name="owner",
                                value="huggingface",
                            ),
                            Binding(
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


expected_function_argument_set = """
{
  lib,
  buildPythonPackage,
  fetchFromGitHub,

  # build-system
  setuptools,
  setuptools-scm,

  # dependencies
  accelerate,
  datasets,
  rich,
  transformers,
}:
{ }
""".strip("\n")


def test_function_argument_set():
    assert (
        FunctionDefinition(
            argument_set=[
                Identifier(name="lib"),
                Identifier(name="buildPythonPackage"),
                Identifier(name="fetchFromGitHub"),
                Identifier(
                    name="setuptools",
                    before=[
                        empty_line,
                        Comment(text="build-system"),
                    ],
                ),
                Identifier(name="setuptools-scm"),
                Identifier(
                    name="accelerate",
                    before=[
                        empty_line,
                        Comment(text="dependencies"),
                    ],
                ),
                Identifier(name="datasets"),
                Identifier(name="rich"),
                Identifier(name="transformers"),
            ]
        ).rebuild()
        == expected_function_argument_set
    )


expected_from_test_issue = """

{
  pname = "trl";

  /*
  We love
  multiline comments
  here
  */

  dependencies = [
    acc
  ];
}
""".strip("\n")


def test_issue():
    assert (
        AttributeSet(
            values=[
                Binding(name="pname", value=Primitive(value="trl")),
                Binding(
                    name="dependencies",
                    value=NixList(
                        value=[
                            Identifier(name="acc"),
                        ],
                    ),
                    before=[
                        empty_line,
                        MultilineComment(text="\nWe love\nmultiline comments\nhere\n"),
                        empty_line,
                    ],
                ),
            ],
        ).rebuild()
        == expected_from_test_issue
    )


def test_nested_list():
    assert (
        (
            NixList(
                value=[
                    Binding(name="pname", value="trl"),
                    Binding(
                        name="dependencies",
                        value=NixList(
                            value=[
                                Identifier(name="acc"),
                            ]
                        ),
                    ),
                ]
            )
        ).rebuild()
        == """
[
  pname = "trl";
  dependencies = [
    acc
  ];
]
""".strip("\n")
    )
