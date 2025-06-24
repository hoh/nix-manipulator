#!/usr/bin/env python3
"""
nix-attrs-flatten.py – emit a dict that maps each leaf attribute to its value,
including function names along the path, e.g.

    {"stdenv.mkDerivation.src.fetchFromGitHub.hash": "sha256-…", …}

Requires py-tree-sitter ≥ 0.23 and tree_sitter_nix.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Union

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Parser


def extract_text(node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode()


def normalize_function_name(node, code: bytes) -> str:
    """Normalize whitespace in function expressions and handle select expressions."""
    if node.type == "select_expression":
        # For select expressions like stdenv.mkDerivation, combine them
        base = node.child_by_field_name("expression")
        attrpath = node.child_by_field_name("attrpath")
        
        if base and attrpath:
            base_text = extract_text(base, code)
            attr_text = extract_text(attrpath, code)
            return f"{base_text}.{attr_text}"
    
    return re.sub(r"\s+", "", extract_text(node, code))


def parse_nix_value(value_str: str) -> Any:
    """Convert Nix value string to appropriate Python type."""
    value_str = value_str.strip()

    # Handle quoted strings
    if len(value_str) >= 2 and value_str[0] in ('"', "'") and value_str[-1] == value_str[0]:
        return value_str[1:-1]

    # Handle literals
    literals = {"true": True, "false": False, "null": None}
    if value_str.lower() in literals:
        return literals[value_str.lower()]

    # Handle numbers
    try:
        return int(value_str) if '.' not in value_str else float(value_str)
    except ValueError:
        pass

    # Handle simple single-item lists: [ "item" ]
    simple_list = re.match(r'^\[\s*"([^"]+)"\s*\]$', value_str)
    if simple_list:
        return [simple_list.group(1)]

    # Handle multi-line lists
    if re.match(r'^\[\s*\n(\s+[^\n]+\n)+\s*\]$', value_str):
        items = re.findall(r'\s+([^\s][^\n]*)', value_str)
        cleaned_items = []
        for item in items:
            item = item.strip()
            if item == "]":
                continue
            if item.endswith("]"):
                item = item.rstrip("]").strip()
            cleaned_items.append(parse_nix_value(item))
        return cleaned_items

    return value_str


def extract_attributes(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Recursively extract attributes from Nix AST."""
    node_type = node.type

    if node_type == "comment":
        return

    if node_type == "function_expression":
        # Skip the parameter and go to the body
        body = node.child_by_field_name("body")
        if body:
            extract_attributes(body, code, path_prefix, results)

    elif node_type == "parenthesized_expression":
        # Skip parentheses and process the inner expression
        for child in node.children:
            if child.type not in ["(", ")"]:
                extract_attributes(child, code, path_prefix, results)

    elif node_type == "apply_expression":
        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")

        if function_node and argument_node:
            # Handle select_expression (like stdenv.mkDerivation)
            if function_node.type == "select_expression":
                function_name = normalize_function_name(function_node, code).replace(".", "")
            else:
                function_name = normalize_function_name(function_node, code)
            
            new_path = path_prefix + [function_name]
            extract_attributes(argument_node, code, new_path, results)

    elif node_type == "select_expression":
        # Handle dot notation like lib.licenses.mit
        if path_prefix:
            key = ".".join(path_prefix)
            results[key] = extract_text(node, code).strip()

    elif node_type in {"attrset_expression", "rec_attrset_expression"}:
        # Find binding_set child
        binding_set = next((child for child in node.children if child.type == "binding_set"), None)
        if not binding_set:
            return

        for binding in binding_set.children:
            if binding.type == "binding":
                attr_path = binding.child_by_field_name("attrpath")
                expression = binding.child_by_field_name("expression")

                if not attr_path or not expression:
                    continue

                # Extract attribute path components
                components = []
                for part in attr_path.children:
                    if part.type == "identifier":
                        components.append(extract_text(part, code))
                
                full_path = path_prefix + components
                
                # Process based on expression type
                if expression.type in {
                    "attrset_expression", "rec_attrset_expression",
                    "apply_expression", "function_expression", 
                    "parenthesized_expression"
                }:
                    extract_attributes(expression, code, full_path, results)
                else:
                    # Leaf value
                    attribute_key = ".".join(full_path)
                    results[attribute_key] = extract_text(expression, code).strip()

    elif node_type in {"list_expression", "string_expression", "variable_expression", "with_expression"}:
        # Handle these as leaf values if we have a path
        if path_prefix:
            key = ".".join(path_prefix)
            results[key] = extract_text(node, code).strip()

    else:
        # Handle any other leaf expressions
        if path_prefix:
            key = ".".join(path_prefix)
            results[key] = extract_text(node, code).strip()


def flatten_nix_file(file_path: Path) -> dict[str, str]:
    """Parse a Nix file and return flattened attributes."""
    source_code = file_path.read_bytes()

    # Set up tree-sitter parser
    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)

    # debug_ast(tree.root_node, source_code)

    # Extract attributes
    attributes = {}
    cursor = tree.walk()

    if cursor.goto_first_child():
        while True:
            extract_attributes(cursor.node, source_code, [], attributes)
            if not cursor.goto_next_sibling():
                break

    return attributes


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Flatten Nix attributes from a file")
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", choices=["json", "text"], default="text",
                        help="Output format (default: text)")
    args = parser.parse_args()

    # Process file
    raw_attributes = flatten_nix_file(Path(args.file))
    processed_attributes = {key: parse_nix_value(value) for key, value in raw_attributes.items()}

    # Output results
    if args.output == "json":
        print(json.dumps(processed_attributes, indent=2))
    else:
        for key, value in sorted(processed_attributes.items()):
            print(f"{key}: {value}")


def debug_ast(node, code: bytes, indent=0):
    """Debug helper to print AST structure."""
    prefix = "  " * indent
    text_preview = extract_text(node, code)[:50].replace('\n', '\\n')
    print(f"{prefix}{node.type}: '{text_preview}...'")
    
    for child in node.children:
        debug_ast(child, code, indent + 1)


if __name__ == "__main__":
    main()