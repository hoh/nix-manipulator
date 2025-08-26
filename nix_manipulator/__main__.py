#!/usr/bin/env python3
"""
High-level example usage of the Nix manipulator library.
"""

import sys

from pygments.lexers import NixLexer, PythonLexer

from nix_manipulator.cli import build_parser
from nix_manipulator.expressions import NixSourceCode
from nix_manipulator.manipulations import remove_value, set_value
from nix_manipulator.parser import parse


def main(args=None):
    parser = build_parser()
    args = parser.parse_args(args)

    source: NixSourceCode
    match args.command:
        case "shell":
            print("Launching Nix shell...")
            # TODO
        case "set":
            source = parse(args.file.read())
            return set_value(
                source=source,
                npath=args.npath,
                value=args.value,
            )
        case "rm":
            source = parse(args.file.read())
            return remove_value(
                source=source,
                npath=args.npath,
            )
        case "test":
            original = args.file.read().strip("\n")
            source = parse(original)
            rebuild = source.rebuild().strip("\n")

            if original == rebuild:
                return "OK"
            else:
                return "Fail"
        case _:
            parser.print_help(sys.stderr)


if __name__ == "__main__":
    main()
