from pathlib import Path
from tempfile import NamedTemporaryFile

from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.set import NixAttributeSet
from nix_manipulator.expressions.binding import NixBinding
from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.identifier import NixIdentifier
from nix_manipulator.expressions.function.definition import FunctionDefinition

from .fixtures import nixpkgs_trl_default

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
                NixIdentifier(name="lib"),
                NixIdentifier(name="buildPythonPackage"),
                NixIdentifier(name="fetchFromGitHub"),
                NixIdentifier(
                    name="setuptools",
                    before=[
                        empty_line,
                        Comment(text="build-system"),
                    ],
                ),
                NixIdentifier(name="setuptools-scm"),
                NixIdentifier(
                    name="accelerate",
                    before=[
                        empty_line,
                        Comment(text="dependencies"),
                    ],
                ),
                NixIdentifier(name="datasets"),
                NixIdentifier(name="rich"),
                NixIdentifier(name="transformers"),
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
        NixAttributeSet(
            values=[
                NixBinding(name="pname", value=Primitive(value="trl")),
                NixBinding(
                    name="dependencies",
                    value=NixList(
                        value=[
                            NixIdentifier(name="acc"),
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
                    NixBinding(name="pname", value="trl"),
                    NixBinding(
                        name="dependencies",
                        value=NixList(
                            value=[
                                NixIdentifier(name="acc"),
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


def test_function_definition():
    function = nixpkgs_trl_default
    print(function.rebuild())

    with NamedTemporaryFile() as f:
        f.write(function.rebuild().encode() + b"\n")
        f.seek(0)

        assert function.rebuild() == f.read().decode().strip("\n")
