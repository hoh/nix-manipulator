#!/usr/bin/env python3
"""
Nix parser that recursively extracts the structure of a Nix expression into a
Python object, and then rebuilds the Nix code from it.
"""

import argparse
import pprint
from pathlib import Path
from typing import Any, Dict, Set

import tree_sitter_nix as ts_nix
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer
from pygments.lexers.python import PythonLexer
from tree_sitter import Language, Parser


class NixExpression:
    """Base class for Nix expressions."""
    pass


class NixFunction(NixExpression):
    """Represents a Nix function with its components."""

    def __init__(self):
        self.arguments: Set['NixVariable'] = set()
        self.let_bindings: Dict[str, Any] = {}
        self.result: Any = None

    def __repr__(self):
        return (f"NixFunction(arguments={sorted(list(self.arguments), key=lambda v: v.name)!r}, "
                f"let_bindings={self.let_bindings!r}, result={self.result!r})")


class NixVariable(NixExpression):
    """Represents a Nix variable reference."""

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"NixVariable('{self.name}')"

    def __eq__(self, other):
        if not isinstance(other, NixVariable):
            return NotImplemented
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)


class NixAttrSet(NixExpression, dict):
    """Represents a Nix attribute set."""
    pass


class NixApply(NixExpression):
    """Represents a Nix function application."""

    def __init__(self, function: Any, argument: Any):
        self.function = function
        self.argument = argument

    def __repr__(self) -> str:
        return f"NixApply(function={self.function!r}, argument={self.argument!r})"


def extract_text(node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode('utf-8')


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
        result = NixAttrSet()
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
        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")

        if function_node and argument_node:
            function_obj = parse_nix_expression(function_node, code)
            argument_obj = parse_nix_expression(argument_node, code)
            return NixApply(function_obj, argument_obj)
        return None

    elif node_type == "function_expression":
        nix_func = NixFunction()
        param_node = node.child_by_field_name("formals")
        body_node = node.child_by_field_name("body")

        if param_node:
            nix_func.arguments = extract_function_arguments(param_node, code)

        if body_node:
            if body_node.type == "let_expression":
                nix_func.let_bindings = extract_let_bindings(body_node, code)
                result_node = body_node.child_by_field_name("body")
                if result_node:
                    nix_func.result = parse_nix_expression(result_node, code)
            else:
                nix_func.result = parse_nix_expression(body_node, code)
        return nix_func

    elif node_type == "string_expression":
        text = extract_text(node, code)
        # This doesn't handle escaped quotes inside the string
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        if text.startswith("''") and text.endswith("''"):
            return text[2:-2]
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
        return NixVariable(text)

    else:
        return extract_text(node, code).strip()


def extract_function_arguments(param_node, code: bytes) -> Set[NixVariable]:
    """Extract argument names from function parameters."""
    arguments = set()
    if not param_node:
        return arguments

    for child in param_node.children:
        if child.type == "formal":
            arg_text = extract_text(child, code).strip().strip(',')
            if arg_text and not arg_text.startswith("#"):
                arguments.add(NixVariable(arg_text))
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


def parse_nix_file(file_path: Path) -> Any:
    """Parse a Nix file and return a Nix expression object."""
    source_code = file_path.read_bytes()

    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)

    root_node = tree.root_node
    if root_node.type == "source_code" and root_node.children:
        return parse_nix_expression(root_node.children[0], source_code)
    return None


def rebuild_expression(expr: Any, indent_level=0) -> str:
    """Recursively rebuilds a Nix code string from a Python object."""
    indent = "  " * indent_level
    next_indent = "  " * (indent_level + 1)

    if isinstance(expr, NixVariable):
        return expr.name
    elif isinstance(expr, str):
        if '\n' in expr:
            return f"''\n{expr}\n''"
        return f'"{expr}"'
    elif isinstance(expr, bool):
        return "true" if expr else "false"
    elif expr is None:
        return "null"
    elif isinstance(expr, (int, float)):
        return str(expr)
    elif isinstance(expr, list):
        if not expr:
            return "[]"
        items = [rebuild_expression(item, indent_level + 1) for item in expr]
        return f"[\n{next_indent}" + f"\n{next_indent}".join(items) + f"\n{indent}]"
    elif isinstance(expr, NixApply):
        func_str = rebuild_expression(expr.function, indent_level)
        if isinstance(expr.argument, (NixAttrSet, dict)) or isinstance(expr.argument, NixFunction):
            arg_str = rebuild_expression(expr.argument, indent_level)
            return f"{func_str} ({arg_str})"
        else:
            arg_str = rebuild_expression(expr.argument, indent_level)
            return f"{func_str} {arg_str}"
    elif isinstance(expr, (NixAttrSet, dict)):
        if not expr:
            return "{ }"
        lines = []
        for key, value in sorted(expr.items()):
            key_str = f'"{key}"' if "." in key else key
            val_str = rebuild_expression(value, indent_level + 1)
            lines.append(f'{next_indent}{key_str} = {val_str};')
        return f"{{\n" + "\n".join(lines) + f"\n{indent}}}"
    elif isinstance(expr, NixFunction):
        return rebuild_function(expr, indent_level)
    else:
        return str(expr)


def rebuild_function(nix_function: NixFunction, indent_level=0) -> str:
    """Rebuilds a Nix code string from a NixFunction object."""
    indent = "  " * indent_level
    next_indent = "  " * (indent_level + 1)

    args_list = sorted([arg.name for arg in nix_function.arguments])
    args_str = ", ".join(args_list)
    header = f"{{ {args_str} }}:"

    if nix_function.let_bindings:
        let_lines = []
        for key, value in sorted(nix_function.let_bindings.items()):
            val_str = rebuild_expression(value, indent_level + 2)
            let_lines.append(f"{next_indent}  {key} = {val_str};")
        let_block = f"{next_indent}let\n" + "\n".join(let_lines) + f"\n{next_indent}in"
        result_str = rebuild_expression(nix_function.result, indent_level + 1)
        body = f"{let_block}\n{result_str}"
    else:
        body = rebuild_expression(nix_function.result, indent_level + 1)

    return f"{header}\n{body}"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file, print its object representation, and then rebuild the Nix code."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    args = parser.parse_args()

    parsed_expr = parse_nix_file(Path(args.file))

    print("--- Parsed Python Object ---")
    formatted_obj = pprint.pformat(parsed_expr, indent=2, width=100)
    print(highlight(formatted_obj, PythonLexer(), TerminalFormatter()))

    print("\n--- Rebuilt Nix Code ---")
    rebuilt_code = rebuild_expression(parsed_expr, indent_level=0)
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))


if __name__ == "__main__":
    main()