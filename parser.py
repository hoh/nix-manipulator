#!/usr/bin/env python3
"""
Nix function parser that recursively extracts function structure and outputs it as JSON.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Set

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Parser


class NixExpression:
    """Base class for Nix expressions."""
    pass


class NixFunction(NixExpression):
    """Represents a Nix function with its components."""

    def __init__(self):
        self.arguments: Set[str] = set()
        self.let_bindings: Dict[str, Any] = {}
        self.result: Dict[str, Any] = {}


def extract_text(node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode()


def parse_nix_expression(node, code: bytes) -> Any:
    """Recursively parse a Nix expression node into a Python object."""
    if not node:
        return None

    node_type = node.type

    if node_type == "parenthesized_expression":
        inner_expr = next((child for child in node.children if child.type not in ["(", ")"]), None)
        return parse_nix_expression(inner_expr, code)

    elif node_type == "list_expression":
        return [parse_nix_expression(child, code) for child in node.named_children]

    elif node_type in {"attrset_expression", "rec_attrset_expression"}:
        result = {}
        binding_set = next((child for child in node.children if child.type == "binding_set"), None)
        if not binding_set:
            return result

        for binding in binding_set.children:
            if binding.type == "binding":
                attr_path = binding.child_by_field_name("attrpath")
                expression = binding.child_by_field_name("expression")

                if attr_path and expression:
                    name_parts = [extract_text(part, code) for part in attr_path.children if part.type == "identifier"]
                    if name_parts:
                        key = ".".join(name_parts)
                        result[key] = parse_nix_expression(expression, code)
        return result

    elif node_type == "apply_expression":
        result = {}
        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")

        if function_node and argument_node:
            func_name = extract_text(function_node, code).strip()
            result["_function_call"] = func_name

            parsed_args = parse_nix_expression(argument_node, code)
            if isinstance(parsed_args, dict):
                result.update(parsed_args)
            else:
                result["_argument"] = parsed_args
        return result

    elif node_type == "string_expression":
        text = extract_text(node, code)
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text

    elif node_type == "integer":
        return int(extract_text(node, code))

    elif node_type == "float":
        return float(extract_text(node, code))

    elif node_type == "variable_expression":
        text = extract_text(node, code)
        if text == "true":
            return True
        elif text == "false":
            return False
        elif text == "null":
            return None
        return text

    else:
        return extract_text(node, code).strip()


def extract_function_arguments(param_node, code: bytes) -> Set[str]:
    """Extract argument names from function parameters."""
    arguments = set()
    if not param_node:
        return arguments

    for child in param_node.children:
        if child.type == "formal":
            arg_text = extract_text(child, code).strip()
            arg_name = arg_text.strip(',')
            if arg_name and not arg_name.startswith("#"):
                arguments.add(arg_name)
    return arguments


def extract_let_bindings(let_node, code: bytes) -> Dict[str, Any]:
    """Extract let bindings from a let expression."""
    bindings = {}
    if not let_node or let_node.type != "let_expression":
        return bindings

    binding_set_node = next((child for child in let_node.children if child.type == "binding_set"), None)

    if not binding_set_node:
        return bindings

    for binding in binding_set_node.children:
        if binding.type == "binding":
            attr_path = binding.child_by_field_name("attrpath")
            expression = binding.child_by_field_name("expression")

            if attr_path and expression:
                name_parts = [extract_text(part, code) for part in attr_path.children if part.type == "identifier"]
                if name_parts:
                    key = ".".join(name_parts)
                    bindings[key] = parse_nix_expression(expression, code)
    return bindings


def parse_nix_file(file_path: Path) -> NixFunction:
    """Parse a Nix file and return a NixFunction instance."""
    source_code = file_path.read_bytes()

    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)

    nix_func = NixFunction()
    root_node = tree.root_node

    if root_node.type == "source_code" and root_node.children:
        func_expr_node = root_node.children[0]
        if func_expr_node.type == "function_expression":
            param_node = func_expr_node.child_by_field_name("formals")
            body_node = func_expr_node.child_by_field_name("body")

            if param_node:
                nix_func.arguments = extract_function_arguments(param_node, source_code)

            if body_node:
                if body_node.type == "let_expression":
                    nix_func.let_bindings = extract_let_bindings(body_node, source_code)
                    result_node = body_node.child_by_field_name("body")
                    if result_node:
                        nix_func.result = parse_nix_expression(result_node, source_code)
                else:
                    nix_func.result = parse_nix_expression(body_node, source_code)

    return nix_func


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Parse Nix function structure and output as JSON")
    parser.add_argument("file", help="Path to the Nix file to process")
    args = parser.parse_args()

    nix_function = parse_nix_file(Path(args.file))

    output_dict = {
        "arguments": sorted(list(nix_function.arguments)),
        "let_bindings": nix_function.let_bindings,
        "result": nix_function.result,
    }

    print(json.dumps(output_dict, indent=2))


if __name__ == "__main__":
    main()