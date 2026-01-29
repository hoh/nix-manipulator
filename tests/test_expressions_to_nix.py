from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binary import BinaryExpression
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.if_expression import IfExpression
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.operator import Operator
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.with_statement import WithStatement
from tests.nixfmt_helpers import validate_nixfmt_rfc


def test_rebuild_nix_identifier():
    """Why: lock in rebuild nix identifier behavior to prevent regressions."""
    assert Identifier(name="foo").rebuild() == "foo"
    assert Identifier(name="foo-bar").rebuild() == "foo-bar"
    assert Identifier(name="foo.bar").rebuild() == "foo.bar"
    assert Identifier(
        name="accelerate",
        before=[
            empty_line,
            Comment(text="dependencies"),
        ],
    ).rebuild() == validate_nixfmt_rfc("""# dependencies\naccelerate""")


def test_rebuild_nix_list():
    """Why: lock in rebuild nix list behavior to prevent regressions."""
    assert NixList(
        value=[
            Identifier(name="foo"),
            Identifier(name="bar"),
        ],
    ).rebuild() == validate_nixfmt_rfc("[\n  foo\n  bar\n]")


def test_rebuild_nix_list_multiline():
    """Why: lock in rebuild nix list multiline behavior to prevent regressions."""
    assert NixList(
        value=[
            Identifier(name="foo"),
            Identifier(name="bar"),
            Identifier(name="baz"),
            Identifier(name="qux"),
            Identifier(name="quux"),
        ],
    ).rebuild() == validate_nixfmt_rfc("""[\n  foo\n  bar\n  baz\n  qux\n  quux\n]""")


def test_rebuild_nix_list_multiline_not_specified():
    """Why: lock in rebuild nix list multiline not specified behavior to prevent regressions."""
    # Long lists should expand by default.
    assert NixList(
        value=[
            Identifier(name="foo"),
            Identifier(name="bar"),
            Identifier(name="baz"),
            Identifier(name="qux"),
            Identifier(name="quux"),
        ]
    ).rebuild() == validate_nixfmt_rfc("""[\n  foo\n  bar\n  baz\n  qux\n  quux\n]""")


def test_nix_with():
    """Why: lock in nix with behavior to prevent regressions."""
    assert WithStatement(
        environment=Identifier(name="lib.maintainers"),
        body=NixList(value=[Identifier(name="hoh")]),
    ).rebuild() == validate_nixfmt_rfc("""with lib.maintainers; [ hoh ]""")


def test_nix_with_multiple_attributes():
    """Why: lock in nix with multiple attributes behavior to prevent regressions."""
    assert WithStatement(
        environment=Identifier(name="lib.maintainers"),
        body=NixList(
            value=[Identifier(name="hoh"), Identifier(name="mic92")],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        """with lib.maintainers;\n[\n  hoh\n  mic92\n]"""
    )


def test_if_expression_inline():
    """Why: lock in if/else expression formatting to prevent regressions."""
    assert (
        IfExpression(
            condition=Identifier(name="cond"),
            consequence=Identifier(name="foo"),
            alternative=Identifier(name="bar"),
        ).rebuild()
        == "if cond then foo else bar"
    )


def test_if_expression_multiline_condition():
    """Why: lock in multiline if/else expression formatting."""
    assert IfExpression(
        condition=BinaryExpression(
            left=Identifier(name="cond1"),
            right=Identifier(name="cond2"),
            operator=Operator(name="&&", before=[Comment(text="note")]),
            operator_gap_lines=1,
        ),
        consequence=Identifier(name="foo"),
        alternative=Identifier(name="bar"),
        condition_gap="\n  ",
        after_if_gap="\n",
        before_then_gap="\n",
        then_gap="\n  ",
        before_else_gap="\n",
        else_gap="\n  ",
    ).rebuild() == validate_nixfmt_rfc(
        """
if
  cond1
  # note
  && cond2
then
  foo
else
  bar
""".strip("\n")
    )


def test_nix_binding():
    """Why: lock in nix binding behavior to prevent regressions."""
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
            ),
        ).rebuild()
        == "foo = [ bar baz ];"
    )


def test_nix_binding_float_and_null_values():
    """Why: allow programmatic floats and nulls to round-trip safely."""
    assert Binding(name="foo", value=1.5).rebuild() == "foo = 1.5;"
    assert Binding(name="bar", value=None).rebuild() == "bar = null;"


def test_nix_comment():
    """Why: lock in nix comment behavior to prevent regressions."""
    assert Comment(text="foo").rebuild() == "# foo"
    assert Comment(text="foo\nbar").rebuild() == "# foo\n# bar"
    assert Primitive(
        value=True,
        before=[
            Comment(text="Many tests require internet access."),
            empty_line,
        ],
    ).rebuild() == validate_nixfmt_rfc(
        """# Many tests require internet access.\n\ntrue"""
    )

    assert (
        Binding(
            name="alice", value="bob", before=[Comment(text="This is a comment")]
        ).rebuild()
        == '# This is a comment\nalice = "bob";'
    )


def test_nix_string_escaping():
    """Why: escape programmatic strings to avoid invalid Nix or interpolation."""
    binding = Binding(
        name="foo",
        value='quote "hi" ${name} backslash \\ end\n\t',
    )
    assert (
        binding.rebuild() == 'foo = "quote \\"hi\\" ${name} backslash \\\\ end\\n\\t";'
    )


def test_binding_inline_comment_after_semicolon():
    """Why: keep binding semicolons on the value line for RFC compliance."""
    binding = Binding(
        name="foo",
        value=Identifier(
            name="bar",
            after=[Comment(text="note", inline=True)],
        ),
    )
    assert binding.rebuild() == "foo = bar; # note"


def test_binding_comment_before_value_forces_newline():
    """Why: comments before values should force multiline layout."""
    value = Primitive(value=1, before=[Comment(text="note")])
    binding = Binding(name="a", value=value)
    assert binding.rebuild() == "a =\n  # note\n  1;"


def test_nix_comment_after_identifier():
    """Why: lock in nix comment after identifier behavior to prevent regressions."""
    assert Identifier(
        name="alice", after=[Comment(text="This is a comment")]
    ).rebuild() == validate_nixfmt_rfc("alice\n# This is a comment")


def test_nix_comment_before_and_after_identifier():
    """Why: lock in nix comment before and after identifier behavior to prevent regressions."""
    assert Identifier(
        name="alice",
        before=[Comment(text="A first comment"), empty_line],
        after=[empty_line, Comment(text="This is a comment")],
    ).rebuild() == validate_nixfmt_rfc(
        """# A first comment\n\nalice\n\n# This is a comment"""
    )


def test_nix_expression():
    """Why: lock in nix expression behavior to prevent regressions."""
    assert Primitive(value=True, before=[]).rebuild() == "true"


def test_nix_set():
    """Why: lock in nix set behavior to prevent regressions."""
    assert AttributeSet(
        values=[
            Binding(name="foo", value=Identifier(name="bar")),
            Binding(
                name="baz",
                value=NixList(
                    value=[
                        Identifier(name="qux"),
                        Identifier(name="quux"),
                    ],
                ),
            ),
        ],
    ).rebuild() == validate_nixfmt_rfc(
        "{\n  foo = bar;\n  baz = [\n    qux\n    quux\n  ];\n}"
    )


def test_nix_set_from_dict():
    assert AttributeSet(
        {"foo": "bar", "baz": ["qux", "quux"]}
    ).rebuild() == validate_nixfmt_rfc(
        '{\n  foo = "bar";\n  baz = [\n    "qux"\n    "quux"\n  ];\n}'
    )


def test_nix_set_attrpath_binding_style():
    """Why: keep single-segment attrpath bindings distinct from explicit nesting."""
    attrpath_binding = Binding(
        name="foo",
        value=AttributeSet(
            values=[
                Binding(
                    name="bar",
                    value=1,
                )
            ],
        ),
        nested=True,
    )
    assert AttributeSet(
        values=[attrpath_binding], multiline=False
    ).rebuild() == validate_nixfmt_rfc("{ foo.bar = 1; }")


def test_nix_set_attrpath_binding_style_deep():
    """Why: keep multi-segment attrpath bindings in attrpath form."""
    deep_attrpath_binding = Binding(
        name="foo",
        value=AttributeSet(
            values=[
                Binding(
                    name="bar",
                    value=AttributeSet(
                        values=[
                            Binding(
                                name="baz",
                                value=1,
                            )
                        ],
                    ),
                    nested=True,
                )
            ],
        ),
        nested=True,
    )
    assert AttributeSet(
        values=[deep_attrpath_binding], multiline=False
    ).rebuild() == validate_nixfmt_rfc("{ foo.bar.baz = 1; }")


def test_nix_set_attrpath_binding_style_intermediate_explicit():
    """Why: stop attrpath expansion when a nested segment is explicit."""
    explicit_binding = Binding(
        name="foo",
        value=AttributeSet(
            values=[
                Binding(
                    name="bar",
                    value=AttributeSet(values=[Binding(name="baz", value=1)]),
                    nested=False,
                )
            ],
        ),
        nested=True,
    )
    assert AttributeSet(values=[explicit_binding]).rebuild() == validate_nixfmt_rfc(
        """
{
  foo.bar = {
    baz = 1;
  };
}
""".strip("\n")
    )


def test_nix_set_explicit_nested_binding_style():
    """Why: keep explicit nested sets distinct from attrpath bindings."""
    explicit_binding = Binding(
        name="foo",
        value=AttributeSet(values=[Binding(name="bar", value=1)]),
    )
    assert AttributeSet(values=[explicit_binding]).rebuild() == validate_nixfmt_rfc(
        "{\n  foo = {\n    bar = 1;\n  };\n}"
    )


def test_nix_set_nested_explicit_and_attrpath_mix():
    """Why: preserve mixed explicit and attrpath bindings within nested sets."""
    nested = Binding(
        name="a",
        value=AttributeSet(
            values=[
                Binding(name="b", value=1),
                Binding(name="c", value=2),
                Binding(
                    name="d",
                    value=AttributeSet(
                        values=[
                            Binding(
                                name="e",
                                value=3,
                            )
                        ],
                    ),
                    nested=True,
                ),
                Binding(
                    name="f",
                    value=AttributeSet(values=[Binding(name="g", value=4)]),
                ),
            ],
        ),
    )
    assert AttributeSet(values=[nested]).rebuild() == validate_nixfmt_rfc(
        """
{
  a = {
    b = 1;
    c = 2;
    d.e = 3;
    f = {
      g = 4;
    };
  };
}
""".strip("\n")
    )


def test_nix_function_definition_empty_set():
    """Why: lock in nix function definition empty set behavior to prevent regressions."""
    # Empty sets as input and output
    assert FunctionDefinition(
        argument_set=[],
        output=AttributeSet(values=[]),
    ).rebuild() == validate_nixfmt_rfc("{ }: { }")


def test_nix_function_definition_one_binding():
    """Why: lock in nix function definition one binding behavior to prevent regressions."""
    assert FunctionDefinition(
        argument_set=[Identifier(name="pkgs")],
        output=AttributeSet(
            values=[
                Binding(name="pkgs", value=Identifier(name="pkgs")),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc("{ pkgs }:\n{\n  pkgs = pkgs;\n}")


def test_nix_function_with_named_attribute_set():
    """Why: lock in nix function with named attribute set behavior to prevent regressions."""
    assert (
        FunctionDefinition(
            argument_set=[Identifier(name="pkgs")],
            named_attribute_set=Identifier(name="args"),
            named_attribute_set_before_formals=True,
            output=AttributeSet(
                values=[
                    Binding(name="pkgs-copy", value=Identifier(name="pkgs")),
                ],
            ),
        )
    ).rebuild() == validate_nixfmt_rfc("args@{ pkgs }:\n{\n  pkgs-copy = pkgs;\n}")


def test_nix_function_with_named_attribute_set_after():
    """Why: lock in nix function with named attribute set after behavior to prevent regressions."""
    assert (
        FunctionDefinition(
            argument_set=[Identifier(name="pkgs")],
            named_attribute_set=Identifier(name="args"),
            named_attribute_set_before_formals=False,
            output=AttributeSet(
                values=[
                    Binding(name="pkgs-copy", value=Identifier(name="pkgs")),
                ],
            ),
        )
    ).rebuild() == validate_nixfmt_rfc("{ pkgs }@args:\n{\n  pkgs-copy = pkgs;\n}")


def test_nix_function_definition_empty_lines_in_argument_set():
    """Why: lock in nix function definition empty lines in argument set behavior to prevent regressions."""
    assert FunctionDefinition(
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
        output=AttributeSet(
            values=[
                Binding(name="pkgs", value=Identifier(name="pkgs")),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        """
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
    """Why: lock in nix function definition let bindings behavior to prevent regressions."""
    assert FunctionDefinition(
        argument_set=[],
        output=AttributeSet(
            values=[],
            scope=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(name="alice", value="bob"),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_let_bindings_from_dict():
    assert FunctionDefinition(
        argument_set=[],
        output=AttributeSet(
            values=[],
            scope={
                "foo": Identifier(name="bar"),
                "alice": "bob",
            },
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ }:\nlet\n  foo = bar;\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings():
    """Why: lock in nix function definition multiple let bindings behavior to prevent regressions."""
    # Let statement with comments
    assert FunctionDefinition(
        argument_set=[],
        output=AttributeSet(
            scope=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
            values=[],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_let_statements_with_comment():
    """Why: lock in nix function definition let statements with comment behavior to prevent regressions."""
    assert FunctionDefinition(
        argument_set=[],
        output=AttributeSet(
            values=[],
            scope=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(
                    name="alice",
                    value="bob",
                    before=[Comment(text="This is a comment")],
                ),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ }:\nlet\n  foo = bar;\n  # This is a comment\n  alice = "bob";\nin\n{ }'
    )


def test_nix_function_definition_multiple_let_bindings_complex():
    """Why: lock in nix function definition multiple let bindings complex behavior to prevent regressions."""
    assert FunctionDefinition(
        argument_set=[Identifier(name="pkgs")],
        output=AttributeSet(
            values=[
                Binding(name="pkgs-again", value=Identifier(name="pkgs-copy")),
            ],
            scope=[
                Binding(name="pkgs-copy", value=Identifier(name="pkgs")),
                Binding(name="alice", value="bob"),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ pkgs }:\nlet\n  pkgs-copy = pkgs;\n  alice = "bob";\nin\n{\n  pkgs-again = pkgs-copy;\n}'
    )


def test_function_call():
    """Why: lock in function call behavior to prevent regressions."""
    assert FunctionCall(
        name="foo",
        argument=AttributeSet(
            values=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(name="alice", value="bob"),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc('foo {\n  foo = bar;\n  alice = "bob";\n}')


def test_function_with_comments():
    """Why: lock in function with comments behavior to prevent regressions."""
    assert FunctionCall(
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
    ).rebuild() == validate_nixfmt_rfc(
        'foo {\n  # This is a comment\n  foo = bar;\n  alice = "bob";\n}'
    )


def test_function_definition_with_function_call():
    """Why: lock in function definition with function call behavior to prevent regressions."""
    assert FunctionDefinition(
        argument_set=[Identifier(name="pkgs")],
        output=FunctionCall(
            name="buildPythonPackage",
            recursive=True,
            argument=AttributeSet(
                values=[
                    Binding(name="pkgs", value=Identifier(name="pkgs")),
                    Binding(name="alice", value="bob"),
                ],
            ),
        ),
    ).rebuild() == validate_nixfmt_rfc(
        '{ pkgs }:\nbuildPythonPackage rec {\n  pkgs = pkgs;\n  alice = "bob";\n}'
    )


def test_function_call_recursive():
    """Why: lock in function call recursive behavior to prevent regressions."""
    assert FunctionCall(
        name="foo",
        recursive=True,
        argument=AttributeSet(
            values=[
                Binding(name="foo", value=Identifier(name="bar")),
                Binding(name="alice", value="bob"),
            ],
        ),
    ).rebuild() == validate_nixfmt_rfc('foo rec {\n  foo = bar;\n  alice = "bob";\n}')


def test_list():
    """Why: lock in list behavior to prevent regressions."""
    assert NixList(
        value=[
            Identifier(name="setuptools"),
            Identifier(name="setuptools-scm"),
        ],
    ).rebuild() == validate_nixfmt_rfc("[\n  setuptools\n  setuptools-scm\n]")


def test_binding_list():
    """Why: lock in binding list behavior to prevent regressions."""
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
        == "build-system = [ setuptools setuptools-scm ];"
    )


def test_indented_function_call():
    """Why: lock in indented function call behavior to prevent regressions."""
    assert NixList(
        value=[
            FunctionCall(name="fetchFromGitHub"),
        ],
    ).rebuild() == validate_nixfmt_rfc("[ fetchFromGitHub ]")

    assert NixList(
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
                        Binding(
                            name="meta",
                            value=AttributeSet(
                                values=[
                                    Binding(
                                        name="homepage",
                                        value="https://example.invalid",
                                    ),
                                ]
                            ),
                        ),
                    ]
                ),
            ),
        ],
    ).rebuild() == validate_nixfmt_rfc(
        '[\n  fetchFromGitHub\n  {\n    owner = "huggingface";\n    repo = "trl";\n    meta = {\n      homepage = "https://example.invalid";\n    };\n  }\n]'
    )


expected_function_argument_set = validate_nixfmt_rfc(
    """
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
)


def test_function_argument_set():
    """Why: lock in function argument set behavior to prevent regressions."""
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


expected_from_test_issue = validate_nixfmt_rfc(
    """

{
  pname = "trl";

  /*
    We love
    multiline comments
    here
  */

  dependencies = [ acc ];
}
""".strip("\n")
)


def test_issue():
    """Why: lock in issue behavior to prevent regressions."""
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
    """Why: lock in nested list behavior to prevent regressions."""
    assert NixList(
        value=[
            NixList(
                value=[
                    Identifier(name="acc"),
                    Identifier(name="datasets"),
                    Identifier(name="rich"),
                    Identifier(name="transformers"),
                    Identifier(name="torch"),
                ],
            ),
            NixList(
                value=[
                    Identifier(name="setuptools"),
                    Identifier(name="setuptools-scm"),
                    Identifier(name="wheel"),
                    Identifier(name="pip"),
                    Identifier(name="build"),
                ],
            ),
        ]
    ).rebuild() == validate_nixfmt_rfc(
        """
[
  [
    acc
    datasets
    rich
    transformers
    torch
  ]
  [
    setuptools
    setuptools-scm
    wheel
    pip
    build
  ]
]
""".strip("\n")
    )


def test_inherit_single_line():
    """Why: lock in inherit single line behavior to prevent regressions."""
    assert (
        Inherit(
            names=[
                Identifier(name="foo"),
            ]
        ).rebuild()
        == "inherit foo;"
    )


def test_inherit_from_expression():
    """Why: lock in inherit from expression behavior to prevent regressions."""
    assert (
        Inherit(
            from_expression=Identifier(name="attrs"),
            names=[
                Identifier(name="foo"),
            ],
        ).rebuild()
        == "inherit (attrs) foo;"
    )


def test_inherit_from_multiline_expression():
    """Why: lock in inherit from multiline expression behavior to prevent regressions."""
    assert (
        Inherit(
            from_expression=FunctionCall(
                name=FunctionCall(
                    name=Identifier(name="pkgs.callPackage"),
                    argument=Identifier(name="./foo.nix"),
                ),
                argument=AttributeSet(
                    values=[
                        Binding(name="arg", value="val"),
                    ]
                ),
            ),
            names=[
                Identifier(name="attr1"),
                Identifier(name="attr2"),
            ],
        ).rebuild()
        == """
inherit
  (pkgs.callPackage ./foo.nix {
    arg = "val";
  })
  attr1
  attr2
  ;
""".strip("\n")
    )


def test_if_expression_else_if_chain():
    """Why: lock in else-if chain formatting to prevent regressions."""
    assert IfExpression(
        condition=Identifier(name="cond1"),
        consequence=Identifier(name="foo"),
        alternative=IfExpression(
            condition=Identifier(name="cond2"),
            consequence=Identifier(name="bar"),
            alternative=Identifier(name="baz"),
            then_gap="\n  ",
            before_else_gap="\n",
            else_gap="\n  ",
        ),
        then_gap="\n  ",
        before_else_gap="\n",
    ).rebuild() == validate_nixfmt_rfc(
        """
if cond1 then
  foo
else if cond2 then
  bar
else
  baz
""".strip("\n")
    )


def test_binary_expressions():
    """Why: lock in binary expressions behavior to prevent regressions."""
    assert (
        BinaryExpression(
            left=Identifier(name="foo"),
            right=3,
            operator="==",
        ).rebuild()
        == "foo == 3"
    )

    assert (
        BinaryExpression(
            left=Identifier(name="bar"),
            right=4,
            operator="!=",
        ).rebuild()
        == "bar != 4"
    )


def test_assertion_from_python():
    """Why: lock in assertion from python behavior to prevent regressions."""
    assert (
        Assertion(
            expression=BinaryExpression(
                left=Identifier(name="foo"),
                right=Identifier(name="bar"),
                operator="==",
            ),
            body=Primitive(value=True),
        )
    ).rebuild() == "assert foo == bar;\ntrue"


def test_operator():
    """Why: lock in operator behavior to prevent regressions."""
    assert (Operator(name="++")).rebuild() == "++"


def test_operator_with_comment():
    """Why: lock in operator with comment behavior to prevent regressions."""
    assert (
        BinaryExpression(
            left=Identifier(name="foo"),
            right=Identifier(name="bar"),
            operator=Operator(
                name="++",
                before=[
                    Comment(text="This is a comment"),
                ],
            ),
            operator_gap_lines=1,
        )
    ).rebuild() == validate_nixfmt_rfc("foo\n# This is a comment\n++ bar")

    assert (
        AttributeSet(
            values=[
                Binding(
                    name="foo",
                    value=BinaryExpression(
                        left=NixList(
                            value=[
                                Primitive(value=1),
                                Primitive(value=2),
                                Primitive(value=3),
                                Primitive(value=4),
                                Primitive(value=5),
                            ]
                        ),
                        right=NixList(
                            value=[
                                Primitive(value=6),
                            ],
                        ),
                        operator=Operator(
                            name="++", before=[Comment(text="This is a comment")]
                        ),
                        operator_gap_lines=1,
                    ),
                )
            ]
        )
    ).rebuild() == validate_nixfmt_rfc("""{
  foo = [
    1
    2
    3
    4
    5
  ]
  # This is a comment
  ++ [ 6 ];
}""")
