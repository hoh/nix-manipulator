"""CLI package for the Nix manipulator entrypoints."""

from nix_manipulator.cli.main import main
from nix_manipulator.cli.parser import build_parser, with_file_argument

__all__ = ["build_parser", "main", "with_file_argument"]
