from pathlib import Path

from nix_manipulator.symbols import (
    FunctionDefinition,
    FunctionCall,
    NixIdentifier,
    NixList,
    NixAttributeSet,
    NixWith,
    NixBinding,
    NixExpression,
    Comment,
    empty_line,
    MultilineComment,
)


def test_function_definition():
    function = FunctionDefinition(
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
        ],
        let_statements=[
            NixBinding(name="owner", value="huggingface"),
            NixBinding(
                name="acc",
                value=NixIdentifier("accelerate"),
                before=[Comment(text="We love comments here")],
            ),
        ],
        result=FunctionCall(
            name="buildPythonPackage",
            recursive=True,
            argument=NixAttributeSet(
                [
                    NixBinding("pname", "trl"),
                    NixBinding("version", "0.19.0"),
                    NixBinding(
                        "pyproject",
                        NixExpression(
                            value=True,

                        ),
                        before=[
                            Comment(text="This is something else"),
                        ],
                    ),
                    NixBinding(
                        "src",
                        FunctionCall(
                            name="fetchFromGitHub",
                            argument=NixAttributeSet(
                                values=[
                                    NixBinding(
                                        name="owner",
                                        value=NixIdentifier("owner"),
                                        before=[
                                            Comment(text="Something cool"),
                                        ],
                                    ),
                                    NixBinding("repo", "trl"),
                                    NixBinding("tag", "v${version}"),
                                    NixBinding(
                                        "hash",
                                        "sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=",
                                    ),
                                ]
                            ),
                        ),
                        before=[empty_line],
                    ),
                    NixBinding(
                        "build_system",
                        NixList(
                            value=[
                                NixIdentifier("setuptools"),
                                NixIdentifier("setuptools-scm"),
                            ],
                            before=[empty_line],
                        )
                    ),
                    NixBinding(
                        "dependencies",
                        NixList(
                            value=[
                                NixIdentifier("acc"),
                                NixIdentifier("datasets"),
                                NixIdentifier("rich"),
                                NixIdentifier("transformers"),
                            ],
                            before=[
                                empty_line,
                                MultilineComment(
                                    text="\nWe love\nmultiline comments\nhere\n"
                                ),
                                empty_line,
                            ],
                        )
                    ),
                    NixBinding(
                        "doCheck",
                        NixExpression(
                            value=False,
                            before=[
                                empty_line,
                                Comment(text="Many tests require internet access."),
                            ],
                        )
                    ),
                    NixBinding(
                        "pythonImportsCheck",
                        NixList(
                            value=["trl"],
                            before=[empty_line],
                        )
                    ),
                    NixBinding(
                        "meta",
                        NixAttributeSet(
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
                            before=[empty_line],
                        )
                    ),
                ]
            ),
        ),
    )
    print(function.rebuild())
    (Path(__file__).parent / "nix_files/trl-default-new-generated.nix").write_text(function.rebuild())
    assert (
            function.rebuild()
            == (Path(__file__).parent / "nix_files/trl-default-new.nix").read_text()
    )
