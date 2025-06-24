#!/usr/bin/env python3
"""
nix-attrs-flatten.py – emit a dict that maps each leaf attribute to its value,
including function names along the path, e.g.

    {"stdenv.mkDerivation.src.fetchFromGitHub.hash": "sha256-…", …}

Requires py-tree-sitter ≥ 0.23  and tree_sitter_nix.
"""

from pathlib import Path
import sys, re
from tree_sitter import Parser, Language
import tree_sitter_nix as ts_nix
import argparse
import logging

logger = logging.getLogger(__name__)


# ───────────────────────── helpers ──────────────────────────
def text(node, code: bytes) -> str:
    """Return the exact source substring for *node*."""
    return code[node.start_byte:node.end_byte].decode()


def func_name(node, code: bytes) -> str:
    """Collapse whitespace inside the function part of an apply_expression."""
    return re.sub(r"\s+", "", text(node, code))


# Add a helper function to print node structure for debugging
def print_node_structure(node, code, indent=0):
    logger.debug(" " * indent + f"Node: {node.type}")
    for child_idx in range(node.child_count):
        child = node.children[child_idx]
        logger.debug(" " * (indent + 2) + f"Child {child_idx}: {child.type}")
        if child.type == "binding_set":
            logger.debug(" " * (indent + 4) + "Contents of binding_set:")
            for binding_idx in range(child.child_count):
                binding = child.children[binding_idx]
                logger.debug(" " * (indent + 6) + f"Binding {binding_idx}: {binding.type}")


# ───────────────────── recursive traversal ───────────────────
def walk_expr(node, code: bytes, prefix: list[str], out: dict[str, str]):
    t = node.type
    logger.debug(f"Processing node type: {t} with prefix: {prefix}")
    
    # Skip comments
    if t == "comment":
        return
        
    if t == "function_expression":
        # Handle function expressions by walking into their body
        body = node.child_by_field_name("body")
        if body:
            logger.debug(f"Found function body of type: {body.type}")
            walk_expr(body, code, prefix, out)
        
    elif t == "apply_expression":
        fn = node.child_by_field_name("function")
        arg = node.child_by_field_name("argument")
        fn_name_str = func_name(fn, code)
        logger.debug(f"Found apply_expression with function: {fn_name_str}")
        walk_expr(arg, code, prefix + [fn_name_str], out)

    elif t in {"attrset_expression", "rec_attrset_expression"}:
        logger.debug(f"Processing {t}")
        # Print structure to debug
        print_node_structure(node, code)
        
        # Find the binding_set child
        binding_set = None
        for child in node.children:
            if child.type == "binding_set":
                binding_set = child
                break
        
        if binding_set:
            logger.debug(f"Found binding_set with {binding_set.child_count} children")
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
                        logger.debug(f"Found binding: {key}")
                        
                        if val:
                            if val.type in {"attrset_expression", "rec_attrset_expression", 
                                          "apply_expression", "function_expression"}:
                                walk_expr(val, code, full_path, out)
                            else:
                                value = text(val, code).strip()
                                out[key] = value
                                logger.debug(f"Added leaf: {key} = {value}")

    else:
        # Any other expression is a leaf (strings, numbers, paths, identifiers…)
        if prefix:                          # ignore bare source_code etc.
            key = ".".join(prefix)
            value = text(node, code).strip()
            out[key] = value
            logger.debug(f"Added leaf: {key} = {value}")


# ────────────────────────── main API ─────────────────────────
def flatten(path: Path) -> dict[str, str]:
    logger.debug(f"Processing file: {path}")  # Debug output
    code = path.read_bytes()
    
    # Initialize tree-sitter with proper way for newer versions
    language = Language(ts_nix.language())
    parser = Parser(language)
    
    tree = parser.parse(code)
    logger.debug(f"Parsed tree: {tree.root_node.type}")

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
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level (default: INFO)")
    parser.add_argument("-o", "--output", choices=["json", "text"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
    
    # Set a global verbose flag
    VERBOSE = args.verbose
    
    # Configure logging
    logging_level = getattr(logging, args.log_level)
    if VERBOSE and logging_level > logging.DEBUG:
        # If verbose is set and log level is higher than DEBUG, set to DEBUG
        logging_level = logging.DEBUG
    
    logging.basicConfig(
        level=logging_level,
        format='%(levelname)s: %(message)s'
    )
    
    logger.debug(f"Starting to process: {args.file}")
        
    attrs = flatten(Path(args.file))
    
    if not attrs:
        print("\nNo attributes were found. This could mean:")
        print("1. The Nix file doesn't contain attribute sets in the expected format")
        print("2. The parser needs additional handling for your specific Nix structure")
        if VERBOSE:
            logger.debug("\nTo debug further, examine the node types printed above.")
    else:
        if args.output == "json":
            import json
            print(json.dumps(attrs, indent=2))
        else:
            print(f"\nFound {len(attrs)} attributes")
            for k in sorted(attrs):
                print(f"{k}: {attrs[k]}")