"""
Nix Manipulator Library

A powerful Python library for parsing, manipulating, and reconstructing Nix source code
with high-level abstractions while preserving formatting and comments.
"""

from .parser import parse_nix_cst, parse_nix_file, pretty_print_cst
from .converter import convert_nix_source, convert_nix_file, CstToSymbolConverter
from .symbols import (
    NixObject, FunctionDefinition, NixIdentifier, Comment, MultilineComment,
    NixBinding, NixSet, FunctionCall, NixExpression, NixList, NixWith,
    empty_line, linebreak, comma
)

__version__ = "0.1.0"
__all__ = [
    # Parser functions
    "parse_nix_cst",
    "parse_nix_file",
    "pretty_print_cst",

    # Converter functions
    "convert_nix_source",
    "convert_nix_file",
    "CstToSymbolConverter",

    # Symbol classes
    "NixObject",
    "FunctionDefinition",
    "NixIdentifier",
    "Comment",
    "MultilineComment",
    "NixBinding",
    "NixSet",
    "FunctionCall",
    "NixExpression",
    "NixList",
    "NixWith",

    # Trivia objects
    "empty_line",
    "linebreak",
    "comma",
]