#!/usr/bin/env python3
"""
Nix parser that recursively extracts the structure of a Nix expression into a
Python object, preserving order and comments, and then rebuilds the Nix code.
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


class NixNode:
    """Base class for all nodes in our Nix CST representation."""
    pass


class NixTrivia(NixNode):
    """Represents comments or whitespace."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        return f"NixTrivia({self.text!r})"


class NixExpression(NixNode):
    """Base class for Nix expressions."""
    pass


class NixBinding(NixNode):
    """Represents a key-value binding in an attrset or let block."""

    def __init__(self, key: str, value: Any, text: str):
        self.key = key
        self.value = value
        self.text = text  # The full original text of the binding

    def __repr__(self):
        return f"NixBinding(key='{self.key}', value={self.value!r})"


class NixContainer(NixExpression):
    """Base class for nodes that contain other nodes, preserving trivia."""

    def __init__(self):
        self.children: List[NixNode] = []

    def __repr__(self):
        return f"{self.__class__.__name__}(children={self.children!r})"


class NixFunction(NixContainer):
    """Represents a Nix function with its components."""
    pass


class NixAttrSet(NixContainer):
    """Represents a Nix attribute set, preserving order and trivia."""

    def __init__(self, rec=False):
        super().__init__()
        self.rec = rec


class NixApply(NixExpression):
    """Represents a Nix function application."""

    def __init__(self, function: Any, argument: Any):
        self.function = function
        self.argument = argument

    def __repr__(self) -> str:
        return f"NixApply(function={self.function!r}, argument={self.argument!r})"


class NixVerbatim(NixExpression):
    """Represents a Nix expression that we will render verbatim from source."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        return f"NixVerbatim({self.text!r})"


def parse_cst(node: Node, code: bytes) -> NixNode:
    """
    Recursively parse a Tree-sitter node into a Concrete Syntax Tree,
    preserving all comments and whitespace.
    """
    node_type = node.type

    if node_type in {"attrset_expression", "rec_attrset_expression"}:
        container = NixAttrSet(rec=(node_type == "rec_attrset_expression"))
        binding_set = next((c for c in node.children if c.type == "binding_set"), None)
        if binding_set:
            populate_container_from_children(container, binding_set, code)
        return container

    if node_type == "let_expression":
        # A let-in can be treated like a container of bindings followed by a body
        container = NixAttrSet() # Using AttrSet to hold the bindings
        populate_container_from_children(container, node, code)
        body_node = node.child_by_field_name("body")
        # The final child in the container will be the body expression
        if body_node:
            container.children.append(parse_cst(body_node, code))
        return container

    if node_type == "function_expression":
        func = NixFunction()
        populate_container_from_children(func, node, code)
        return func

    if node_type == "apply_expression":
        func_node = node.child_by_field_name("function")
        arg_node = node.child_by_field_name("argument")
        if func_node and arg_node:
            return NixApply(parse_cst(func_node, code), parse_cst(arg_node, code))

    # For simple types, we just return a verbatim representation
    return NixVerbatim(extract_text(node, code))


def populate_container_from_children(container: NixContainer, parent_node: Node, code: bytes):
    """
    Parses the children of a node, capturing all trivia (comments, whitespace)
    between them.
    """
    last_child_end = parent_node.start_byte
    # Find the first meaningful child to establish the real start
    first_child = next((c for c in parent_node.children if not c.is_extra), None)
    if first_child:
        last_child_end = first_child.start_byte

    for child in parent_node.children:
        # Capture text between the last node and this one as trivia
        trivia_text = code[last_child_end:child.start_byte].decode('utf-8')
        if trivia_text:
            container.children.append(NixTrivia(trivia_text))

        # Process the actual child node
        if child.type == "binding":
            key_node = child.child_by_field_name("attrpath")
            value_node = child.child_by_field_name("expression")
            if key_node and value_node:
                key = extract_text(key_node, code)
                value = parse_cst(value_node, code)
                container.children.append(NixBinding(key, value, extract_text(child, code)))
        elif not child.is_extra and child.type not in ["binding_set", "{", "}", "let", "in", ":"]:
            # Add other significant nodes if they are not part of a larger structure
            # we are already handling (like 'binding').
            container.children.append(parse_cst(child, code))

        last_child_end = child.end_byte

    # Capture any final trivia after the last child
    final_trivia = code[last_child_end:parent_node.end_byte].decode('utf-8')
    if final_trivia:
        container.children.append(NixTrivia(final_trivia))


def parse_nix_file(file_path: Path) -> Optional[NixNode]:
    """Parse a Nix file and return the root of its CST."""
    source_code = file_path.read_bytes()
    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)
    root_node = tree.root_node

    if root_node.type == "source_code" and root_node.children:
        # Find the first actual expression node, skipping any leading trivia
        main_expr_node = next((c for c in root_node.children if not c.is_extra), None)
        if main_expr_node:
            # We create a root container to hold the main expression and all trivia
            root_container = NixContainer()
            populate_container_from_children(root_container, root_node, source_code)
            return root_container
    return None


def rebuild_from_cst(node: NixNode) -> str:
    """Recursively rebuilds a Nix code string from a CST node."""
    if isinstance(node, NixTrivia):
        return node.text
    if isinstance(node, NixVerbatim):
        return node.text
    if isinstance(node, NixBinding):
        return node.text  # The binding is preserved exactly as it was
    if isinstance(node, NixContainer):
        return "".join(rebuild_from_cst(child) for child in node.children)
    if isinstance(node, NixApply):
        func_str = rebuild_from_cst(node.function)
        arg_str = rebuild_from_cst(node.argument)
        # This is a simplification; a full solution would need to reconstruct
        # the original text between function and arg if it contained comments.
        return f"{func_str} {arg_str}"

    return ""


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file, print its object representation, and then rebuild the Nix code."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", help="Path to the output file for the rebuilt Nix code")
    args = parser.parse_args()

    parsed_cst = parse_nix_file(Path(args.file))

    print("--- Parsed Python Object (CST) ---")
    # Using repr for a dense but complete view of the object
    print(highlight(repr(parsed_cst), PythonLexer(), TerminalFormatter()))

    print("\n--- Rebuilt Nix Code ---")
    if parsed_cst:
        rebuilt_code = rebuild_from_cst(parsed_cst)
        print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(rebuilt_code, encoding='utf-8')
            print(f"\n--- Rebuilt Nix code written to {output_path} ---")


if __name__ == "__main__":
    main()