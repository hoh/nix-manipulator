#!/usr/bin/env python3

import argparse
from pathlib import Path

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer
from pygments.lexers.python import PythonLexer

from nix_manipulator.parser import parse_nix_file, pretty_print_cst


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file and rebuild it, preserving all formatting."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", help="Path to the output file for the rebuilt Nix code")
    args = parser.parse_args()

    parsed_cst = parse_nix_file(Path(args.file))

    if not parsed_cst:
        return

    print("--- Parsed Python Object (CST Representation) ---")
    pretty_cst_string = pretty_print_cst(parsed_cst)
    print(highlight(pretty_cst_string, PythonLexer(), TerminalFormatter()))

    print("\n--- Rebuilt Nix Code ---")
    rebuilt_code = parsed_cst.rebuild()
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))

    if args.output:
        output_path = Path(args.output)
        try:
            output_path.write_text(rebuilt_code, encoding='utf-8')
            print(f"\n--- Rebuilt Nix code written to {output_path} ---")
        except IOError as e:
            print(f"\nError writing to output file {output_path}: {e}")


if __name__ == "__main__":
    main()