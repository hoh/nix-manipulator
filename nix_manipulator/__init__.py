"""
Nix-Manipulator

A Python library for parsing, manipulating, and reconstructing Nix source code
with high-level abstractions while preserving formatting and comments in RFC-formatted code.
"""

# NOTE: parse_to_ast is an internal diagnostic helper and intentionally
# not exported as a stable public API.
from nix_manipulator.parser import parse, parse_file

__all__ = ["parse", "parse_file"]
