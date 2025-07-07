from pathlib import Path

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Node, Parser

from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.source_code import NixSourceCode
from nix_manipulator.mapping import tree_sitter_node_to_expression

# Initialize the tree-sitter parser only once for efficiency.
NIX_LANGUAGE = Language(ts_nix.language())
PARSER = Parser(NIX_LANGUAGE)


def parse_to_ast(source_code: bytes | str) -> Node:
    """Parse Nix source code and return the root of its AST."""
    code_bytes = (
        source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    )
    tree = PARSER.parse(code_bytes)
    return tree.root_node


def parse(source_code: bytes | str | Path) -> NixExpression | NixSourceCode:
    """Parse Nix source code and return the root of its AST."""
    if isinstance(source_code, Path):
        source_code = source_code.read_text()
    return tree_sitter_node_to_expression(parse_to_ast(source_code=source_code))
