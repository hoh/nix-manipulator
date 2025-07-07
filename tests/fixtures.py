from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.with_statement import NixWith
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.set import NixAttributeSet
from nix_manipulator.expressions.binding import NixBinding
from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.identifier import NixIdentifier
from nix_manipulator.expressions.function.definition import FunctionDefinition

nixpkgs_trl_default = FunctionDefinition(
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
            value=NixIdentifier(name="accelerate"),
            before=[Comment(text="We love comments here")],
        ),
    ],
    output=FunctionCall(
        name="buildPythonPackage",
        recursive=True,
        argument=NixAttributeSet(
            values=[
                NixBinding(name="pname", value="trl"),
                NixBinding(name="version", value="0.19.0"),
                NixBinding(
                    name="pyproject",
                    value=Primitive(
                        value=True,
                    ),
                    before=[
                        Comment(text="This is something else"),
                    ],
                ),
                NixBinding(
                    name="src",
                    value=FunctionCall(
                        name="fetchFromGitHub",
                        argument=NixAttributeSet(
                            values=[
                                NixBinding(
                                    name="owner",
                                    value=NixIdentifier(name="owner"),
                                    before=[
                                        Comment(text="Something cool"),
                                    ],
                                ),
                                NixBinding(name="repo", value="trl"),
                                NixBinding(name="tag", value="v${version}"),
                                NixBinding(
                                    name="hash",
                                    value="sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=",
                                ),
                            ]
                        ),
                    ),
                    before=[empty_line],
                ),
                NixBinding(
                    name="build-system",
                    value=NixList(
                        value=[
                            NixIdentifier(name="setuptools"),
                            NixIdentifier(name="setuptools-scm"),
                        ],
                    ),
                    before=[empty_line],
                ),
                NixBinding(
                    name="dependencies",
                    value=NixList(
                        value=[
                            NixIdentifier(name="acc"),
                            NixIdentifier(name="datasets"),
                            NixIdentifier(name="rich"),
                            NixIdentifier(name="transformers"),
                        ],
                    ),
                    before=[
                        empty_line,
                        MultilineComment(
                            text="\n  We love\n  multiline comments\n  here\n"
                        ),
                        empty_line,
                    ],
                ),
                NixBinding(
                    name="doCheck",
                    value=Primitive(
                        value=False,
                    ),
                    before=[
                        empty_line,
                        Comment(text="Many tests require internet access."),
                    ],
                ),
                NixBinding(
                    name="pythonImportsCheck",
                    value=NixList(
                        value=["trl"],
                        multiline=False,
                    ),
                    before=[empty_line],
                ),
                NixBinding(
                    name="meta",
                    value=NixAttributeSet.from_dict(
                        {
                            "description": "Train transformer language models with reinforcement learning",
                            "homepage": "https://github.com/huggingface/trl",
                            "changelog": "https://github.com/huggingface/trl/releases/tag/${src.tag}",
                            "license": NixIdentifier(name="lib.licenses.asl20"),
                            "maintainers": NixWith(
                                environment=NixIdentifier(name="lib.maintainers"),
                                body=NixList(
                                    value=[NixIdentifier(name="hoh")], multiline=False
                                ),
                            ),
                        },
                    ),
                    before=[empty_line],
                ),
            ]
        ),
    ),
)
