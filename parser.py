#!/usr/bin/env python3
"""
Nix function parser that extracts function structure and outputs it as JSON.
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

    binding_set = let_node.child_by_field_name("bindings")
    if not binding_set:
        return bindings

    for binding in binding_set.children:
        if binding.type == "binding":
            attr_path = binding.child_by_field_name("attrpath")
            expression = binding.child_by_field_name("expression")

            if attr_path and expression:
                name_parts = [extract_text(part, code) for part in attr_path.children if part.type == "identifier"]
                if name_parts:
                    key = ".".join(name_parts)
                    bindings[key] = extract_text(expression, code).strip()
    return bindings


def extract_result_set(node, code: bytes) -> Dict[str, Any]:
    """Extract the result attribute set from an expression."""
    result = {}
    if not node:
        return result

    if node.type in {"attrset_expression", "rec_attrset_expression"}:
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
                        if expression.type in {"attrset_expression", "rec_attrset_expression"}:
                            result[key] = extract_result_set(expression, code)
                        else:
                            result[key] = extract_text(expression, code).strip()

    elif node.type == "apply_expression":
        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")

        if function_node and argument_node:
            func_name = extract_text(function_node, code).strip()
            result["_function_call"] = func_name
            if argument_node.type in {"attrset_expression", "rec_attrset_expression"}:
                nested_result = extract_result_set(argument_node, code)
                result.update(nested_result)

    return result


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
                        nix_func.result = extract_result_set(result_node, source_code)
                else:
                    nix_func.result = extract_result_set(body_node, source_code)

    return nix_func


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Parse Nix function structure and output as JSON")
    parser.add_argument("file", help="Path to the Nix file to process")
    args = parser.parse_args()

    nix_function = parse_nix_file(Path(args.file))

    # Create a dictionary representation of the NixFunction object
    output_dict = {
        "arguments": sorted(list(nix_function.arguments)),
        "let_bindings": nix_function.let_bindings,
        "result": nix_function.result,
    }

    # Print as a formatted JSON string, which is valid Python syntax for a dict.
    print(json.dumps(output_dict, indent=2))


if __name__ == "__main__":
    main()