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

nixpkgs_trl_default = FunctionDefinition(
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
    ],
    output=FunctionCall(
        name="buildPythonPackage",
        recursive=True,
        scope=[
            Binding(name="owner", value="huggingface"),
            Binding(
                name="acc",
                value=Identifier(name="accelerate"),
                before=[Comment(text="We love comments here")],
            ),
        ],
        argument=AttributeSet(
            values=[
                Binding(name="pname", value="trl"),
                Binding(name="version", value="0.19.0"),
                Binding(
                    name="pyproject",
                    value=Primitive(
                        value=True,
                    ),
                    before=[
                        Comment(text="This is something else"),
                    ],
                ),
                Binding(
                    name="src",
                    value=FunctionCall(
                        name="fetchFromGitHub",
                        argument=AttributeSet(
                            values=[
                                Binding(
                                    name="owner",
                                    value=Identifier(name="owner"),
                                    before=[
                                        Comment(text="Something cool"),
                                    ],
                                ),
                                Binding(name="repo", value="trl"),
                                Binding(name="tag", value="v${version}"),
                                Binding(
                                    name="hash",
                                    value="sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=",
                                ),
                            ]
                        ),
                    ),
                    before=[empty_line],
                ),
                Binding(
                    name="build-system",
                    value=NixList(
                        value=[
                            Identifier(name="setuptools"),
                            Identifier(name="setuptools-scm"),
                        ],
                    ),
                    before=[empty_line],
                ),
                Binding(
                    name="dependencies",
                    value=NixList(
                        value=[
                            Identifier(name="acc"),
                            Identifier(name="datasets"),
                            Identifier(name="rich"),
                            Identifier(name="transformers"),
                        ],
                    ),
                    before=[
                        empty_line,
                        MultilineComment(
                            text="\nWe love\nmultiline comments\nhere\n"
                        ),
                        empty_line,
                    ],
                ),
                Binding(
                    name="doCheck",
                    value=Primitive(
                        value=False,
                    ),
                    before=[
                        empty_line,
                        Comment(text="Many tests require internet access."),
                    ],
                ),
                Binding(
                    name="pythonImportsCheck",
                    value=NixList(
                        value=["trl"],
                    ),
                    before=[empty_line],
                ),
                Binding(
                    name="meta",
                    value=AttributeSet.from_dict(
                        {
                            "description": "Train transformer language models with reinforcement learning",
                            "homepage": "https://github.com/huggingface/trl",
                            "changelog": "https://github.com/huggingface/trl/releases/tag/${src.tag}",
                            "license": Identifier(name="lib.licenses.asl20"),
                            "maintainers": WithStatement(
                                environment=Identifier(name="lib.maintainers"),
                                body=NixList(
                                    value=[Identifier(name="hoh")],
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
