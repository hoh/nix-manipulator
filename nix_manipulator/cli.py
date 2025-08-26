import argparse
import sys


def with_file_argument(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-f",
        "--file",
        type=argparse.FileType("r"),
        metavar="FILE",
        default=sys.stdin,
        help="Read the Nix input from FILE instead of stdin",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nima",
        description="Nix Manipulator – A tool for manipulating Nix expressions",
        epilog="For more information, visit https://github.com/hoh/nima",
    )

    # Each sub‑command lives in its own sub‑parser.
    subparsers = parser.add_subparsers(
        dest="command",  # parsed result → args.command
        required=False,  # force a sub‑command
        help="Nix Manipulator commands",
    )

    shell_parser = subparsers.add_parser(
        "shell", help="Open a preconfigured Python shell"
    )
    with_file_argument(shell_parser)

    set_parser = subparsers.add_parser("set", help="Replace an expression")
    set_parser.add_argument("npath", help="NPath to the expression to replace")
    set_parser.add_argument("value", help="New value for the expression")
    with_file_argument(set_parser)

    rm_parser = subparsers.add_parser("rm", help="Remove an expression")
    rm_parser.add_argument("npath", help="NPath to the expression to replace")
    with_file_argument(rm_parser)

    test_parser = subparsers.add_parser(
        "test", help="Test if an expression can be rebuild"
    )
    with_file_argument(test_parser)

    return parser
