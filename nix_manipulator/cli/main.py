"""
High-level example usage of the Nix manipulator library.
"""

import code
import sys

from nix_manipulator.cli.manipulations import remove_value, set_value
from nix_manipulator.cli.parser import build_parser
from nix_manipulator.expressions import NixSourceCode
from nix_manipulator.parser import parse


def main(args=None) -> int:
    """Return CLI exit codes so automation can distinguish success from failure."""
    parser = build_parser()
    args = parser.parse_args(args)

    source: NixSourceCode
    match args.command:
        case "shell":
            shell_locals = {
                "parse": parse,
                "set_value": set_value,
                "remove_value": remove_value,
                "NixSourceCode": NixSourceCode,
            }
            if args.file is not sys.stdin:
                source_text = args.file.read()
                if source_text:
                    shell_locals["source_text"] = source_text
                    shell_locals["source"] = parse(source_text)
            code.interact(
                banner="Nix Manipulator shell (parse, set_value, remove_value, NixSourceCode)",
                local=shell_locals,
            )
            return 0
        case "set":
            source = parse(args.file.read())
            print(
                set_value(
                    source=source,
                    npath=args.npath,
                    value=args.value,
                )
            )
            return 0
        case "rm":
            source = parse(args.file.read())
            print(
                remove_value(
                    source=source,
                    npath=args.npath,
                )
            )
            return 0
        case "test":
            original = args.file.read()
            source = parse(original)
            if source.contains_error:
                print("Fail")
                return 1
            rebuild = source.rebuild()

            if original == rebuild:
                print("OK")
                return 0
            print("Fail")
            return 1
        case _:
            parser.print_help(sys.stderr)
            return 2
