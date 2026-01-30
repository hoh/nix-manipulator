import ctypes
from pathlib import Path
from threading import local

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Node, Parser

from nix_manipulator.expressions.path import source_path_context
from nix_manipulator.expressions.source_code import NixSourceCode


def _capsule_from_pointer(ptr: int) -> object:
    """Wrap legacy pointer bindings so newer tree-sitter avoids deprecated int paths."""
    pycapsule_new = ctypes.pythonapi.PyCapsule_New
    pycapsule_new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    pycapsule_new.restype = ctypes.py_object
    return pycapsule_new(ctypes.c_void_p(ptr), b"tree_sitter.Language", None)


def _load_language() -> Language:
    """Normalize grammar bindings so parser setup stays warning-free across packaging."""
    language = ts_nix.language()
    if isinstance(language, Language):
        return language
    if isinstance(language, int):
        return Language(_capsule_from_pointer(language))
    return Language(language)


# Initialize the tree-sitter parser language once and cache parsers per thread.
NIX_LANGUAGE = _load_language()
_PARSER_LOCAL = local()


def _get_parser() -> Parser:
    """Provide a per-thread parser to avoid shared-state parsing races."""
    parser = getattr(_PARSER_LOCAL, "parser", None)
    if parser is None:
        parser = Parser(NIX_LANGUAGE)
        _PARSER_LOCAL.parser = parser
    return parser


def parse_to_ast(source_code: bytes | str) -> Node:
    """Parse Nix source code and return the root of its AST (internal diagnostic helper)."""
    code_bytes = (
        source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    )
    parser = _get_parser()
    tree = parser.parse(code_bytes)
    return tree.root_node


def parse(
    source_code: bytes | str, source_path: Path | str | None = None
) -> NixSourceCode:
    """Parse Nix source code and return the root of its AST."""
    node = parse_to_ast(source_code=source_code)
    source = NixSourceCode.from_cst(node)
    if source_path:
        source.source_path = Path(source_path)
    return source


def parse_file(path: Path | str) -> NixSourceCode:
    """Parse a Nix file from disk with UTF-8 decoding."""
    path = Path(path)
    source_code = path.read_text(encoding="utf-8")
    with source_path_context(path):
        source = parse(source_code, source_path=path)
    return source
