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


class NixNode:
    """Base class for all nodes in our Nix AST representation."""

    def __init__(self):
        self.leading_comments: List[str] = []

    def add_leading_comments(self, comments: List[str]):
        if comments:
            self.leading_comments.extend(comments)


class NixExpression(NixNode):
    """Base class for Nix expressions."""
    pass


class NixBinding(NixNode):
    """Represents a key-value binding in an attrset or let block."""

    def __init__(self, key: str, value: Any):
        super().__init__()
        self.key = key
        self.value = value

    def __repr__(self):
        return f"NixBinding(key='{self.key}', value={self.value!r}, comments={len(self.leading_comments)})"


class NixFunction(NixExpression):
    """Represents a Nix function with its components."""

    def __init__(self):
        super().__init__()
        self.arguments: List['NixArgument'] = []
        self.let_bindings: List[NixBinding] = []
        self.result: Any = None

    def __repr__(self):
        return (f"NixFunction(arguments={self.arguments!r}, "
                f"let_bindings={self.let_bindings!r}, result={self.result!r})")


class NixVariable(NixExpression):
    """Represents a Nix variable reference."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __repr__(self) -> str:
        return f"NixVariable('{self.name}')"


class NixArgument(NixVariable):
    """Represents a function argument, which is a variable."""

    def __repr__(self) -> str:
        return f"NixArgument('{self.name}')"


class NixAttrSet(NixExpression):
    """Represents a Nix attribute set, preserving order."""

    def __init__(self):
        super().__init__()
        self.rec = False
        self.bindings: List[NixBinding] = []

    def __repr__(self) -> str:
        return f"NixAttrSet(rec={self.rec}, bindings={self.bindings!r})"


class NixApply(NixExpression):
    """Represents a Nix function application."""

    def __init__(self, function: Any, argument: Any):
        super().__init__()
        self.function = function
        self.argument = argument

    def __repr__(self) -> str:
        return f"NixApply(function={self.function!r}, argument={self.argument!r})"


def extract_text(node: Node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode('utf-8')


def parse_nix_expression(node: Node, code: bytes) -> Any:
    """Recursively parse a Nix expression node into a Python object."""
    node_type = node.type

    if node_type == "parenthesized_expression":
        inner_expr = next((child for child in node.children if child.type not in ["(", ")"]), None)
        return parse_nix_expression(inner_expr, code) if inner_expr else None

    elif node_type == "list_expression":
        items = []
        comments_buffer = []
        for child in node.children:
            if child.type == 'comment':
                comments_buffer.append(extract_text(child, code).strip())
            elif not child.is_extra:
                item = parse_nix_expression(child, code)
                if isinstance(item, NixNode):
                    item.add_leading_comments(comments_buffer)
                comments_buffer = []
                items.append(item)
        return items

    elif node_type in {"attrset_expression", "rec_attrset_expression"}:
        attr_set = NixAttrSet()
        attr_set.rec = node_type == "rec_attrset_expression"
        binding_set_node = next((child for child in node.children if child.type == "binding_set"), None)
        if binding_set_node:
            attr_set.bindings = parse_bindings(binding_set_node, code)
        return attr_set

    elif node_type == "apply_expression":
        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")
        if function_node and argument_node:
            return NixApply(
                parse_nix_expression(function_node, code),
                parse_nix_expression(argument_node, code)
            )

    elif node_type == "function_expression":
        return parse_function(node, code)

    elif node_type == "let_expression":
        nix_func = NixFunction()
        nix_func.let_bindings = parse_bindings(node, code)
        result_node = node.child_by_field_name("body")
        if result_node:
            nix_func.result = parse_nix_expression(result_node, code)
        return nix_func # Represent let-in as a body-only function

    elif node_type == "string_expression":
        text = extract_text(node, code)
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        if text.startswith("''") and text.endswith("''"):
            return text[2:-2].strip()
        return text

    elif node_type == "integer": return int(extract_text(node, code))
    elif node_type == "float": return float(extract_text(node, code))
    elif node_type == "variable_expression":
        text = extract_text(node, code)
        if text == "true": return True
        if text == "false": return False
        if text == "null": return None
        return NixVariable(text)

    return extract_text(node, code).strip()


def parse_bindings(parent_node: Node, code: bytes) -> List[NixBinding]:
    """Extracts bindings from an attrset or let-in expression."""
    bindings = []
    binding_set_node = next((n for n in parent_node.children if n.type == "binding_set"), parent_node)
    if not binding_set_node:
        return bindings

    comments_buffer = []
    for child in binding_set_node.children:
        if child.type == 'comment':
            comments_buffer.append(extract_text(child, code).strip())
        elif child.type == "binding":
            attr_path_node = child.child_by_field_name("attrpath")
            expr_node = child.child_by_field_name("expression")
            if attr_path_node and expr_node:
                key = extract_text(attr_path_node, code)
                value = parse_nix_expression(expr_node, code)
                binding = NixBinding(key, value)
                binding.add_leading_comments(comments_buffer)
                comments_buffer = []
                bindings.append(binding)
    return bindings


def parse_function(func_node: Node, code: bytes) -> NixFunction:
    """Parses a function expression node."""
    nix_func = NixFunction()
    param_node = func_node.child_by_field_name("formals")
    body_node = func_node.child_by_field_name("body")

    if param_node:
        comments_buffer = []
        for child in param_node.children:
            if child.type == 'comment':
                comments_buffer.append(extract_text(child, code).strip())
            elif child.type == "formal":
                arg_name = extract_text(child, code).strip().strip(',')
                if arg_name:
                    arg = NixArgument(arg_name)
                    arg.add_leading_comments(comments_buffer)
                    comments_buffer = []
                    nix_func.arguments.append(arg)

    if body_node:
        if body_node.type == "let_expression":
            nix_func.let_bindings = parse_bindings(body_node, code)
            result_node = body_node.child_by_field_name("body")
            if result_node:
                nix_func.result = parse_nix_expression(result_node, code)
        else:
            nix_func.result = parse_nix_expression(body_node, code)
    return nix_func


def parse_nix_file(file_path: Path) -> Optional[NixNode]:
    """Parse a Nix file and return a Nix expression object."""
    source_code = file_path.read_bytes()
    language = Language(ts_nix.language())
    parser = Parser(language)
    tree = parser.parse(source_code)
    root_node = tree.root_node

    comments_buffer = []
    main_expr_node = None
    if root_node.type == "source_code":
        for child in root_node.children:
            if child.type == 'comment':
                comments_buffer.append(extract_text(child, source_code).strip())
            elif not child.is_extra:
                main_expr_node = child
                break
    if main_expr_node:
        parsed_expr = parse_nix_expression(main_expr_node, source_code)
        if isinstance(parsed_expr, NixNode):
            parsed_expr.add_leading_comments(comments_buffer)
        return parsed_expr
    return None


def rebuild_expression(expr: Any, indent_level=0) -> str:
    """Recursively rebuilds a Nix code string from a Python object."""
    indent = "  " * indent_level
    next_indent = "  " * (indent_level + 1)
    comment_str = "".join(f"{indent}{comment}\n" for comment in getattr(expr, 'leading_comments', []))

    if isinstance(expr, NixVariable):
        content = expr.name
    elif isinstance(expr, str):
        content = f'"{expr}"' if '\n' not in expr else f"''\n{indent}{expr}\n{indent}''"
    elif isinstance(expr, bool):
        content = "true" if expr else "false"
    elif expr is None:
        content = "null"
    elif isinstance(expr, (int, float)):
        content = str(expr)
    elif isinstance(expr, list):
        items = [rebuild_expression(item, indent_level + 1) for item in expr]
        content = f"[\n{next_indent}" + f"\n{next_indent}".join(items) + f"\n{indent}]" if items else "[]"
    elif isinstance(expr, NixApply):
        func_str = rebuild_expression(expr.function, indent_level)
        arg_str = rebuild_expression(expr.argument, indent_level if isinstance(expr.argument, NixAttrSet) else 0)
        content = f"{func_str} (\n{arg_str}\n{indent})" if isinstance(expr.argument, NixAttrSet) else f"{func_str} {arg_str}"
    elif isinstance(expr, NixAttrSet):
        binder = "rec " if expr.rec else ""
        if not expr.bindings:
            content = f"{binder}{{ }}"
        else:
            lines = [rebuild_expression(b, indent_level + 1) for b in expr.bindings]
            content = f"{binder}{{\n" + "\n".join(lines) + f"\n{indent}}}"
    elif isinstance(expr, NixBinding):
        val_str = rebuild_expression(expr.value, indent_level)
        content = f"{expr.key} = {val_str};"
    elif isinstance(expr, NixFunction):
        content = rebuild_function(expr, indent_level)
    else:
        content = str(expr)

    return f"{comment_str}{indent}{content}" if isinstance(expr, NixBinding) else f"{comment_str}{content}"


def rebuild_function(nix_function: NixFunction, indent_level=0) -> str:
    """Rebuilds a Nix code string from a NixFunction object."""
    indent = "  " * indent_level
    next_indent = "  " * (indent_level + 1)

    header = ""
    if nix_function.arguments:
        args_str = ", ".join(arg.name for arg in nix_function.arguments)
        header = f"{{ {args_str} }}:"

    body_parts = []
    if nix_function.let_bindings:
        let_lines = "\n".join([rebuild_expression(b, indent_level + 2) for b in nix_function.let_bindings])
        body_parts.append(f"{next_indent}let\n{let_lines}\n{next_indent}in")

    if nix_function.result:
        body_parts.append(rebuild_expression(nix_function.result, indent_level + 1))

    body = "\n".join(body_parts)
    return f"{header}\n{body}" if header else body


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file, print its object representation, and then rebuild the Nix code."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    args = parser.parse_args()

    parsed_expr = parse_nix_file(Path(args.file))

    print("--- Parsed Python Object ---")
    # Using repr for a dense but complete view of the object
    print(highlight(repr(parsed_expr), PythonLexer(), TerminalFormatter()))

    print("\n--- Rebuilt Nix Code ---")
    if parsed_expr:
        rebuilt_code = rebuild_expression(parsed_expr)
        print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))


if __name__ == "__main__":
    main()