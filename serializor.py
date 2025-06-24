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
    # String literals - remove quotes
    if value_str.startswith(('"', "'")) and value_str.endswith(('"', "'")):
        return value_str[1:-1]
    
    # Special values
    special_values = {"true": True, "false": False, "null": None}
    if value_str.lower() in special_values:
        return special_values[value_str.lower()]
    
    # Numbers
    try:
        return int(value_str) if '.' not in value_str else float(value_str)
    except ValueError:
        pass
    
    # Simple arrays like [ "trl" ]
    match = re.match(r'^\[\s*"([^"]+)"\s*\]$', value_str)
    if match:
        return [match.group(1)]
    
    return value_str


def process_value(value_str):
    """Process a value string, converting Nix lists to Python lists."""
    # Multi-line list pattern
    if re.match(r'^\[\s*\n(\s+[^\n]+\n)+\s*\]$', value_str):
        items = re.findall(r'\s+([^\s][^\n]*)', value_str)
        cleaned_items = []
        for item in items:
            item = item.strip()
            if item == "]":
                continue
            if item.endswith("]"):
                item = item.rstrip("]").strip()
            cleaned_items.append(convert_value(item))
        return cleaned_items
    
    return convert_value(value_str)


# ───────────────────── recursive traversal ───────────────────
def walk_expr(node, code: bytes, prefix: list[str], out: dict[str, str]):
    t = node.type
    
    if t == "comment":
        return
        
    if t == "function_expression":
        body = node.child_by_field_name("body")
        if body:
            walk_expr(body, code, prefix, out)
        
    elif t == "apply_expression":
        fn = node.child_by_field_name("function")
        arg = node.child_by_field_name("argument")
        fn_name_str = func_name(fn, code)
        walk_expr(arg, code, prefix + [fn_name_str], out)

    elif t in {"attrset_expression", "rec_attrset_expression"}:
        # Find binding_set
        binding_set = next((child for child in node.children if child.type == "binding_set"), None)
        
        if binding_set:
            for binding in binding_set.children:
                if binding.type == "binding":
                    attr = binding.child_by_field_name("attrpath")
                    val = binding.child_by_field_name("expression")
                    
                    if attr:
                        # Get attribute path components
                        comps = [text(part, code) for part in attr.children if part.type != "."]
                        full_path = prefix + comps
                        key = ".".join(full_path)
                        
                        if val:
                            if val.type in {"attrset_expression", "rec_attrset_expression", 
                                          "apply_expression", "function_expression"}:
                                walk_expr(val, code, full_path, out)
                            else:
                                out[key] = text(val, code).strip()

    else:
        # Leaf expression
        if prefix:
            key = ".".join(prefix)
            out[key] = text(node, code).strip()


# ────────────────────────── main API ─────────────────────────
def flatten(path: Path) -> dict[str, str]:
    code = path.read_bytes()
    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(code)

    result = {}
    cur = tree.walk()
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
        processed_attrs = {key: process_value(value) for key, value in attrs.items()}
        print(json.dumps(processed_attrs, indent=2))
    else:
        for k in sorted(attrs):
            print(f"{k}: {process_value(attrs[k])}")