import tree_sitter_nix as ts_nix
from pygments.lexers.nix import NixLexer
from pygments.lexers.python import PythonLexer
from tree_sitter import Language, Parser, Node

from . import models

# Initialize the tree-sitter parser only once for efficiency.
NIX_LANGUAGE = Language(ts_nix.language())
PARSER = Parser(NIX_LANGUAGE)


def parse_nix_cst(source_code: bytes | str):
    """Parse Nix source code and return the root of its CST."""
    code_bytes = (
        source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    )
    tree = PARSER.parse(code_bytes)
    return parse_to_cst(tree.root_node)


def parse_to_cst(node: Node):
    cls = models.NODE_TYPE_TO_CLASS.get(node.type)
    print()
    print("CLS", cls, node.__class__, node.type)

    if not cls:
        raise ValueError(f"Unknown node type: {node.type}")

    obj = cls.from_cst(node)

    return obj
