from pathlib import Path

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Node, Parser

from nix_manipulator.expressions.source_code import NixSourceCode

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


def parse(source_code: bytes | str | Path) -> NixSourceCode:
    """Parse Nix source code and return the root of its AST."""
    if isinstance(source_code, Path):
        source_code = source_code.read_text()
    node = parse_to_ast(source_code=source_code)
    return NixSourceCode.from_cst(node)
