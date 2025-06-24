#!/usr/bin/env python3
"""
nix-attrs-flatten.py – emit a dict that maps each leaf attribute to its value,
including function names along the path, e.g.

    {"stdenv.mkDerivation.src.fetchFromGitHub.hash": "sha256-…", …}

Requires py-tree-sitter ≥ 0.23  and tree_sitter_nix.
"""

import argparse
import re
from pathlib import Path

import tree_sitter_nix as ts_nix
from tree_sitter import Parser, Language


# ───────────────────────── helpers ──────────────────────────
def text(node, code: bytes) -> str:
    """Return the exact source substring for *node*."""
    return code[node.start_byte:node.end_byte].decode()


def func_name(node, code: bytes) -> str:
    """Collapse whitespace inside the function part of an apply_expression."""
    return re.sub(r"\s+", "", text(node, code))


def convert_value(value_str):
    """Convert Nix value string to appropriate Python type."""
    # Handle string literals (remove quotes)
    if value_str.startswith(('"', "'")) and value_str.endswith(('"', "'")):
        return value_str[1:-1]
    
    # Handle special values with a lookup table
    special_values = {
        "true": True,
        "false": False,
        "null": None
    }
    lower_value = value_str.lower()
    if lower_value in special_values:
        return special_values[lower_value]
    
    # Handle numeric values
    try:
        # Try integer first
        if '.' not in value_str:
            return int(value_str)
        # Then try float
        return float(value_str)
    except ValueError:
        pass
    
    # Handle simple array patterns like [ "trl" ]
    simple_array_match = re.match(r'^\[\s*"([^"]+)"\s*\]$', value_str)
    if simple_array_match:
        return [simple_array_match.group(1)]
    
    # Return original value if no conversion applies
    return value_str


# Helper to detect and convert Nix lists to Python lists
def process_value(value_str):
    """Process a value string, converting Nix lists to Python lists."""
    # Check if it's a list pattern [items]
    list_pattern = r'^\[\s*\n(\s+[^\n]+\n)+\s*\]$'
    if re.match(list_pattern, value_str):
        # Extract items from the list
        items = re.findall(r'\s+([^\s][^\n]*)', value_str)
        # Clean up items and check for closing bracket as a separate item
        cleaned_items = []
        for item in items:
            item = item.strip()
            # Skip if the item is just a closing bracket
            if item == "]":
                continue
            # Remove trailing bracket if it's part of an item
            if item.endswith("]"):
                item = item.rstrip("]").strip()
            # Convert each item to appropriate type
            cleaned_items.append(convert_value(item))
        return cleaned_items
    
    # If not a multiline list, try to convert to appropriate type
    return convert_value(value_str)


# ───────────────────── recursive traversal ───────────────────
def walk_expr(node, code: bytes, prefix: list[str], out: dict[str, str]):
    t = node.type
    
    # Skip comments
    if t == "comment":
        return
        
    if t == "function_expression":
        # Handle function expressions by walking into their body
        body = node.child_by_field_name("body")
        if body:
            walk_expr(body, code, prefix, out)
        
    elif t == "apply_expression":
        fn = node.child_by_field_name("function")
        arg = node.child_by_field_name("argument")
        fn_name_str = func_name(fn, code)
        walk_expr(arg, code, prefix + [fn_name_str], out)

    elif t in {"attrset_expression", "rec_attrset_expression"}:
        # Find the binding_set child
        binding_set = None
        for child in node.children:
            if child.type == "binding_set":
                binding_set = child
                break
        
        if binding_set:
            # Process all bindings in the binding_set
            for binding in binding_set.children:
                if binding.type == "binding":
                    attr = binding.child_by_field_name("attrpath")
                    val = binding.child_by_field_name("expression")
                    
                    # Extract attribute name
                    if attr:
                        # Get all parts of the attribute path
                        comps = []
                        for attr_part in attr.children:
                            if attr_part.type != ".":
                                comps.append(text(attr_part, code))
                        
                        full_path = prefix + comps
                        key = ".".join(full_path)
                        
                        if val:
                            if val.type in {"attrset_expression", "rec_attrset_expression", 
                                          "apply_expression", "function_expression"}:
                                walk_expr(val, code, full_path, out)
                            else:
                                value = text(val, code).strip()
                                out[key] = value

    else:
        # Any other expression is a leaf (strings, numbers, paths, identifiers…)
        if prefix:                          # ignore bare source_code etc.
            key = ".".join(prefix)
            value = text(node, code).strip()
            out[key] = value


# ────────────────────────── main API ─────────────────────────
def flatten(path: Path) -> dict[str, str]:
    code = path.read_bytes()
    
    # Initialize tree-sitter with proper way for newer versions
    language = Language(ts_nix.language())
    parser = Parser(language)
    
    tree = parser.parse(code)

    result: dict[str, str] = {}
    cur = tree.walk()                       # skip the `source_code` shell
    if cur.goto_first_child():
        while True:
            walk_expr(cur.node, code, [], result)
            if not cur.goto_next_sibling():
                break
    return result


# ─────────────────────────── CLI ─────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flatten Nix attributes from a file")
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", choices=["json", "text"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
        
    attrs = flatten(Path(args.file))
    
    if args.output == "json":
        import json
        
        # Process values before outputting to JSON
        processed_attrs = {}
        for key, value in attrs.items():
            processed_value = process_value(value)
            processed_attrs[key] = processed_value
            
        print(json.dumps(processed_attrs, indent=2))
    else:
        for k in sorted(attrs):
            processed_value = process_value(attrs[k])
            print(f"{k}: {processed_value}")