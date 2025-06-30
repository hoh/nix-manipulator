from pathlib import Path

from nix_manipulator.symbols import *

def test_function_definition():
    function = FunctionDefinition(
        name="buildPythonPackage",
        recursive=True,
        argument_set=[
            NixIdentifier(name="lib"),
            NixIdentifier(name="buildPythonPackage"),
            NixIdentifier(name="fetchFromGitHub"),
            NixIdentifier(name="setuptools",
                before=[
                    empty_line,
                    Comment(text="build-system"),
                ],
            ),
            NixIdentifier(name="setuptools-scm"),
            NixIdentifier(name="accelerate",
                before=[
                    empty_line,
                    Comment(text="dependencies"),
                ],
            ),
            NixIdentifier(name="datasets"),
            NixIdentifier(name="rich"),
            NixIdentifier(name="transformers"),
        ],
        let_statements=[
            NixBinding(name="owner", value="huggingface"),
            NixBinding(name="acc", value=NixIdentifier("accelerate")),
        ],
        result = NixSet({
            "pname": "trl",
            "version": "0.19.0",
            "pyproject": NixExpression(value=True, before=[
                Comment(text="This is something else"),
            ]),
            "src": FunctionCall(
                name="fetchFromGitHub",
                arguments=[
                    NixBinding(name="owner", value=NixIdentifier("owner"), before=[
                        Comment(text="Something cool"),
                    ]),
                    NixBinding(name="repo", value="trl"),
                    NixBinding(name="tag", value="${version}"),
                    NixBinding(name="hash", value="sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ="),
                ],
                before=[empty_line],
            ),
            "build_system": NixList(
                value = [
                    NixIdentifier("setuptools"),
                    NixIdentifier("setuptools-scm"),
                ],
                before=[empty_line],
            ),
            "dependencies": NixList(
                value= [
                    NixIdentifier("acc"),
                    NixIdentifier("datasets"),
                    NixIdentifier("rich"),
                    NixIdentifier("transformers"),
                ],
                before=[
                    empty_line,
                    MultilineComment(text="\nWe love\nmultiline comments\nhere\n"),
                    empty_line,
                ],
            ),
            "doCheck": NixExpression(
                value=False,
                before=[
                    empty_line,
                    Comment(text="Many tests require internet access."),
                ],
            ),
            "pythonImportsCheck": NixList(
                value=[NixIdentifier("trl")],
                before=[empty_line],
            ),
            "meta": NixSet(
                {
                    "description": "Train transformer language models with reinforcement learning",
                    "homepage": "https://github.com/huggingface/trl",
                    "changelog": "https://github.com/huggingface/trl/releases/tag/${src.tag}",
                    "license": NixIdentifier("mit.licenses.asl20"),
                    "maintainers": NixWith(
                        expression=NixIdentifier("lib.maintainers"),
                        attributes=[NixIdentifier("hoh")],
                    ),
                },
                before=[empty_line]
            )
        }),
    )
    assert function.rebuild() == (Path(__file__).parent / "nix_files/trl-default-old.nix").read_text()
