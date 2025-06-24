#!/usr/bin/env python3
"""
nix-attrs-flatten.py – emit a dict that maps each leaf attribute to its value,
including function names along the path, e.g.

    {"stdenv.mkDerivation.src.fetchFromGitHub.hash": "sha256-…", …}

Requires py-tree-sitter ≥ 0.23  and tree_sitter_nix.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Union

import tree_sitter_nix as ts_nix
from tree_sitter import Parser, Language


# ───────────────────────── helpers ──────────────────────────
def extract_text(node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode()


def normalize_function_name(node, code: bytes) -> str:
    """Normalize whitespace in function expressions."""
    return re.sub(r"\s+", "", extract_text(node, code))


def parse_nix_value(value_str: str) -> Any:
    """Convert Nix value string to appropriate Python type."""
    value_str = value_str.strip()
    
    # Handle quoted strings
    if _is_quoted_string(value_str):
        return value_str[1:-1]
    
    # Handle special literals
    literal_value = _parse_literal(value_str)
    if literal_value is not None:
        return literal_value
    
    # Handle numbers
    number_value = _parse_number(value_str)
    if number_value is not None:
        return number_value
    
    # Handle lists
    list_value = _parse_list(value_str)
    if list_value is not None:
        return list_value
    
    # Return as-is if no conversion applies
    return value_str


def _is_quoted_string(value: str) -> bool:
    """Check if value is a quoted string."""
    return (len(value) >= 2 and 
            value[0] in ('"', "'") and 
            value[-1] == value[0])


def _parse_literal(value: str) -> Union[bool, None, str]:
    """Parse boolean and null literals."""
    literals = {"true": True, "false": False, "null": None}
    return literals.get(value.lower(), None)


def _parse_number(value: str) -> Union[int, float, None]:
    """Parse numeric values."""
    try:
        return int(value) if '.' not in value else float(value)
    except ValueError:
        return None


def _parse_list(value: str) -> Union[list, None]:
    """Parse Nix list expressions."""
    # Simple single-item list: [ "item" ]
    simple_match = re.match(r'^\[\s*"([^"]+)"\s*\]$', value)
    if simple_match:
        return [simple_match.group(1)]
    
    # Multi-line list
    if re.match(r'^\[\s*\n(\s+[^\n]+\n)+\s*\]$', value):
        items = re.findall(r'\s+([^\s][^\n]*)', value)
        return [_clean_list_item(item) for item in items if _is_valid_list_item(item)]
    
    return None


def _clean_list_item(item: str) -> Any:
    """Clean and convert a single list item."""
    item = item.strip()
    if item.endswith("]"):
        item = item.rstrip("]").strip()
    return parse_nix_value(item)


def _is_valid_list_item(item: str) -> bool:
    """Check if item is a valid list element (not just closing bracket)."""
    return item.strip() != "]"


# ───────────────────── recursive traversal ───────────────────
def extract_attributes(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Recursively extract attributes from Nix AST."""
    node_type = node.type
    
    if node_type == "comment":
        return
        
    if node_type == "function_expression":
        _process_function(node, code, path_prefix, results)
        
    elif node_type == "apply_expression":
        _process_application(node, code, path_prefix, results)

    elif node_type in {"attrset_expression", "rec_attrset_expression"}:
        _process_attribute_set(node, code, path_prefix, results)

    else:
        _process_leaf_expression(node, code, path_prefix, results)


def _process_function(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Process function expressions."""
    body = node.child_by_field_name("body")
    if body:
        extract_attributes(body, code, path_prefix, results)


def _process_application(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Process function application expressions."""
    function_node = node.child_by_field_name("function")
    argument_node = node.child_by_field_name("argument")
    
    if function_node and argument_node:
        function_name = normalize_function_name(function_node, code)
        extract_attributes(argument_node, code, path_prefix + [function_name], results)


def _process_attribute_set(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Process attribute set expressions."""
    binding_set = _find_binding_set(node)
    if not binding_set:
        return
        
    for binding in binding_set.children:
        if binding.type == "binding":
            _process_binding(binding, code, path_prefix, results)


def _find_binding_set(node):
    """Find the binding_set child node."""
    return next((child for child in node.children if child.type == "binding_set"), None)


def _process_binding(binding, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Process individual attribute bindings."""
    attr_path = binding.child_by_field_name("attrpath")
    expression = binding.child_by_field_name("expression")
    
    if not attr_path or not expression:
        return
        
    # Extract attribute path components
    components = [extract_text(part, code) for part in attr_path.children if part.type != "."]
    full_path = path_prefix + components
    attribute_key = ".".join(full_path)
    
    # Process based on expression type
    if expression.type in {"attrset_expression", "rec_attrset_expression", 
                          "apply_expression", "function_expression"}:
        extract_attributes(expression, code, full_path, results)
    else:
        results[attribute_key] = extract_text(expression, code).strip()


def _process_leaf_expression(node, code: bytes, path_prefix: list[str], results: dict[str, str]):
    """Process leaf expressions."""
    if path_prefix:
        key = ".".join(path_prefix)
        results[key] = extract_text(node, code).strip()


# ────────────────────────── main API ─────────────────────────
def flatten_nix_file(file_path: Path) -> dict[str, str]:
    """Parse a Nix file and return flattened attributes."""
    source_code = file_path.read_bytes()
    
    # Set up tree-sitter parser
    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)

    # Extract attributes
    attributes = {}
    cursor = tree.walk()
    
    if cursor.goto_first_child():
        while True:
            extract_attributes(cursor.node, source_code, [], attributes)
            if not cursor.goto_next_sibling():
                break
                
    return attributes


def process_attributes(attributes: dict[str, str]) -> dict[str, Any]:
    """Convert raw attribute strings to appropriate Python types."""
    return {key: parse_nix_value(value) for key, value in attributes.items()}


# ─────────────────────────── CLI ─────────────────────────────
def format_output(attributes: dict[str, Any], output_format: str) -> str:
    """Format attributes for output."""
    if output_format == "json":
        return json.dumps(attributes, indent=2)
    else:
        lines = [f"{key}: {value}" for key, value in sorted(attributes.keys())]
        return "\n".join(lines)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Flatten Nix attributes from a file")
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", choices=["json", "text"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
        
    # Process file
    raw_attributes = flatten_nix_file(Path(args.file))
    processed_attributes = process_attributes(raw_attributes)
    
    # Output results
    output = format_output(processed_attributes, args.output)
    print(output)


if __name__ == "__main__":
    main()