#!/usr/bin/env python3
"""
Nix parser that recursively extracts the structure of a Nix expression into a
Python object, preserving order, comments, and all formatting, and then
rebuilds the Nix code.
"""

import argparse
from pathlib import Path
from typing import Any, List, Optional

import tree_sitter_nix as ts_nix
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer
from pygments.lexers.python import PythonLexer
from tree_sitter import Language, Parser, Node


def extract_text(node: Node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode('utf-8')


class CstNode:
    """Base class for all nodes in our Concrete Syntax Tree."""

    def rebuild(self) -> str:
        raise NotImplementedError


class CstContainer(CstNode):
    """A container node that holds a list of other CST nodes."""

    def __init__(self, children: List[CstNode]):
        self.children = children

    def __repr__(self):
        return f"{self.__class__.__name__}(children={self.children!r})"

    def rebuild(self) -> str:
        return "".join(c.rebuild() for c in self.children)


class CstVerbatim(CstNode):
    """A leaf node representing a literal piece of the source code."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        # Keep repr short for readability
        return f"CstVerbatim({self.text.strip()!r})"

    def rebuild(self) -> str:
        return self.text


def parse_to_cst(node: Node, code: bytes) -> CstNode:
    """
    Recursively parse a Tree-sitter node into a Concrete Syntax Tree.
    This CST retains all characters from the original source file, including
    whitespace and comments, ensuring a perfect rebuild.
    """
    # If a node has children, we treat it as a container. We recursively
    # parse its children and also capture the raw text (trivia) between them.
    if node.children:
        children_cst: List[CstNode] = []
        last_child_end = node.start_byte
        for child in node.children:
            # Capture any text (whitespace, comments not part of the AST)
            # that occurred between the last node and the current one.
            trivia = code[last_child_end:child.start_byte].decode()
            if trivia:
                children_cst.append(CstVerbatim(trivia))

            # Recursively parse the child node.
            children_cst.append(parse_to_cst(child, code))

            last_child_end = child.end_byte

        # Capture any final trivia after the last child.
        final_trivia = code[last_child_end:node.end_byte].decode()
        if final_trivia:
            children_cst.append(CstVerbatim(final_trivia))

        return CstContainer(children_cst)

    # If a node has no children, it's a leaf. We represent it as a
    # verbatim chunk of the original source code.
    return CstVerbatim(extract_text(node, code))


def parse_nix_file(file_path: Path) -> Optional[CstNode]:
    """Parse a Nix file and return the root of its CST."""
    try:
        source_code = file_path.read_bytes()
        language = Language(ts_nix.language())
        parser = Parser(language)
        tree = parser.parse(source_code)
        return parse_to_cst(tree.root_node, source_code)
    except Exception as e:
        print(f"Error parsing file {file_path}: {e}")
        return None


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
    # The repr can be very long, so we limit its depth for printing
    print(repr(parsed_cst)[:2000] + "...")

    print("\n--- Rebuilt Nix Code ---")
    rebuilt_code = parsed_cst.rebuild()
    # Highlight and print to console
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