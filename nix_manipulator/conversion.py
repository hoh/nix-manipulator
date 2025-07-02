#!/usr/bin/env python3
"""
Converter from Concrete Syntax Tree (CST) objects to high-level Nix symbols.

This module provides functionality to convert the low-level CST representation
obtained from parse_nix_cst into the high-level symbol objects defined in symbols.py.
The conversion preserves all formatting information including comments, whitespace,
and other trivia by attaching them to the appropriate symbol objects.
"""

import re
from typing import List, Optional, Union, Any
from collections import OrderedDict

from .parser import (
    CstNode, CstContainer, CstElement, CstLeaf, CstVerbatim,
    NixComment, NixIdentifier as CstNixIdentifier, NixString, NixBinding as CstNixBinding,
    NixAttrSet, NixLetIn, NixLambda, NixFormal, parse_nix_cst, parse_nix_file
)

from .symbols import (
    NixObject, FunctionDefinition, NixIdentifier, Comment, MultilineComment,
    NixBinding, NixAttributeSet, FunctionCall, NixExpression, NixList, NixWith,
    empty_line, linebreak, comma
)


class TriviaProcessor:
    """Handles extraction and processing of trivia (comments, whitespace, punctuation)."""

    def extract_trivia(self, node: CstNode) -> List[Any]:
        """Extract trivia from a CST node's post_trivia."""
        trivia_list = []

        for trivia_node in node.post_trivia:
            if isinstance(trivia_node, NixComment):
                comment_text = trivia_node.text.strip()
                if comment_text.startswith('#'):
                    comment_text = comment_text[1:].strip()

                if comment_text.startswith('/*') and comment_text.endswith('*/'):
                    # Multiline comment
                    inner_text = comment_text[2:-2].strip()
                    trivia_list.append(MultilineComment(text=inner_text))
                else:
                    trivia_list.append(Comment(text=comment_text))

            elif isinstance(trivia_node, CstVerbatim):
                text = trivia_node.text

                # Handle different types of trivia
                if ',' in text:
                    trivia_list.append(comma)

                # Count newlines for empty lines
                newline_count = text.count('\n')
                if newline_count > 1:
                    for _ in range(newline_count - 1):
                        trivia_list.append(empty_line)
                elif newline_count == 1:
                    trivia_list.append(linebreak)

        return trivia_list

    def extract_before_trivia(self, container: CstContainer, child_index: int) -> List[Any]:
        """Extract trivia that appears before a specific child in a container."""
        trivia_list = []

        # Look for trivia in preceding verbatim nodes
        for i in range(child_index):
            child = container.children[i]
            if isinstance(child, CstVerbatim):
                text = child.text

                # Extract comments from verbatim text
                comment_pattern = r'#[^\n]*|/\*.*?\*/'
                comments = re.findall(comment_pattern, text, re.DOTALL)

                for comment in comments:
                    if comment.startswith('#'):
                        trivia_list.append(Comment(text=comment[1:].strip()))
                    elif comment.startswith('/*'):
                        inner_text = comment[2:-2]
                        if '\n' in inner_text:
                            trivia_list.append(MultilineComment(text=inner_text))
                        else:
                            trivia_list.append(MultilineComment(text=inner_text.strip()))

                # Handle empty lines
                newline_count = text.count('\n')
                if newline_count > 1:
                    for _ in range(newline_count - 1):
                        trivia_list.append(empty_line)

        return trivia_list


class CstToSymbolConverter:
    """Main converter class that transforms CST nodes to symbol objects."""

    def __init__(self):
        self.trivia_processor = TriviaProcessor()

    def convert(self, cst_root: CstNode) -> NixObject:
        """Convert a CST root node to a high-level symbol object."""
        return self._convert_node(cst_root)

    def _convert_node(self, node: CstNode) -> Union[NixObject, Any]:
        """Convert a single CST node to the appropriate symbol object."""
        if isinstance(node, NixLambda):
            return self._convert_lambda_container(node)
        elif isinstance(node, CstElement) and node.node_type == "lambda":
            return self._convert_lambda(node)
        elif isinstance(node, NixAttrSet):
            return self._convert_attr_set(node)
        elif isinstance(node, CstElement) and node.node_type == "attr_set":
            return self._convert_attr_set_from_element(node)
        elif isinstance(node, NixLetIn):
            return self._convert_let_in(node)
        elif isinstance(node, CstNixBinding):
            return self._convert_binding(node)
        elif isinstance(node, CstElement) and node.node_type == "binding":
            return self._convert_binding(node)
        elif isinstance(node, CstNixIdentifier):
            return self._convert_identifier(node)
        elif isinstance(node, CstElement) and node.node_type == "identifier":
            return self._convert_identifier(node)
        elif isinstance(node, CstElement) and node.node_type == "variable_expression":
            return self._convert_variable_expression(node)
        elif isinstance(node, CstElement) and node.node_type in ("source_code", "source_file"):
            # unwrap top‐level root into its single real child (e.g. a "list")
            children = [c for c in node.children if not getattr(c, "is_trivia", False)]
            if len(children) == 1:
                return self._convert_node(children[0])
            # fall back to treating it as a block of source
            return self._convert_source_code(node)
        elif isinstance(node, CstElement) and node.node_type == "parenthesized":
            return self._convert_parenthesized(node)
        elif isinstance(node, CstElement) and node.node_type == "select_expression":
            return self._convert_select_expression(node)
        elif isinstance(node, NixString):
            return self._convert_string_from_element(node)
        elif isinstance(node, CstElement) and "string" in node.node_type:
            return self._convert_string_from_element(node)
        elif isinstance(node, CstElement) and node.node_type == "application":
            return self._convert_function_call(node)
        elif isinstance(node, CstElement) and node.node_type == "list":
            return self._convert_list(node)
        elif isinstance(node, CstElement) and node.node_type == "with":
            return self._convert_with(node)
        else:
            return self._convert_generic(node)

    def _convert_variable_expression(self, node: CstElement) -> NixObject:
        """Convert a variable expression."""
        # Find the identifier child
        for child in node.children:
            if isinstance(child, CstNixIdentifier):
                return self._convert_identifier(child)
            elif isinstance(child, CstElement) and child.node_type == "identifier":
                return self._convert_identifier(child)

        # Fallback to generic conversion
        return self._convert_generic(node)

    def _convert_source_code(self, node: CstElement) -> NixObject:
        """Convert the root source_code element."""
        # Usually contains a single main expression
        for child in node.children:
            if not isinstance(child, CstVerbatim):
                return self._convert_node(child)

        return self._convert_generic(node)

    def _convert_parenthesized(self, node: CstElement) -> NixObject:
        """Convert a parenthesized expression by extracting its content."""
        # Find the main expression inside parentheses
        for child in node.children:
            if not isinstance(child, CstVerbatim):
                return self._convert_node(child)

        return self._convert_generic(node)

    def _convert_select_expression(self, node: CstElement) -> NixObject:
        """Convert a select expression (e.g., lib.maintainers)."""
        name = self._extract_select_expression_name(node)
        return NixIdentifier(name=name)

    def _convert_string_from_element(self, node: Union[NixString, CstElement]) -> str:
        """Convert a string element to a Python string value."""
        if isinstance(node, NixString):
            text = node.text.strip()
        else:
            text = ""
            for child in node.children:
                if isinstance(child, CstLeaf):
                    text += child.text

        # Remove quotes and handle escape sequences
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.startswith("''") and text.endswith("''"):
            return text[2:-2]

        return text

    def _convert_lambda_container(self, node: NixLambda) -> FunctionDefinition:
        """Convert a NixLambda container to FunctionDefinition."""
        # Extract arguments, let statements, and result from children
        argument_set = []
        let_statements = []
        result = None

        for child in node.children:
            if isinstance(child, NixFormal):
                if child.identifier:
                    arg_name = child.identifier.text.strip()
                    identifier = NixIdentifier(name=arg_name)
                    identifier.before = self.trivia_processor.extract_trivia(child)
                    argument_set.append(identifier)
            elif isinstance(child, NixLetIn):
                let_statements.extend(self._extract_let_bindings(child))
                result = self._extract_let_result(child)
            elif not isinstance(child, CstVerbatim):
                result = self._convert_node(child)

        return FunctionDefinition(
            argument_set=argument_set,
            let_statements=let_statements,
            result=result
        )

    def _convert_lambda(self, node: CstElement) -> FunctionDefinition:
        """Convert a lambda element to FunctionDefinition."""
        argument_set = []
        let_statements = []
        result = None

        # Find formals (argument set)
        formals_node = self._find_child_by_type(node, "formals")
        if formals_node:
            for child in formals_node.children:
                if isinstance(child, CstElement) and child.node_type == "formal":
                    identifier_node = self._find_child_by_type(child, "identifier")
                    if identifier_node:
                        arg_name = self._convert_identifier(identifier_node).name
                        identifier = NixIdentifier(name=arg_name)
                        argument_set.append(identifier)

        # Find body
        body_nodes = [child for child in node.children if not isinstance(child, CstVerbatim) and child != formals_node]
        if body_nodes:
            body_node = body_nodes[-1]  # Usually the last non-trivia child

            if isinstance(body_node, CstElement) and body_node.node_type == "let_in":
                let_statements.extend(self._extract_let_bindings(body_node))
                result = self._extract_let_result(body_node)
            else:
                result = self._convert_node(body_node)

        return FunctionDefinition(
            argument_set=argument_set,
            let_statements=let_statements,
            result=result
        )

    def _convert_let_in(self, node: NixLetIn) -> FunctionDefinition:
        """Convert a let-in expression."""
        let_statements = self._extract_let_bindings(node)
        result = self._extract_let_result(node)

        return FunctionDefinition(
            let_statements=let_statements,
            result=result
        )

    def _extract_let_bindings(self, node: CstContainer) -> List[NixBinding]:
        """Extract bindings from a let expression."""
        bindings = []

        for child in node.children:
            if isinstance(child, CstNixBinding):
                bindings.append(self._convert_binding(child))
            elif isinstance(child, CstElement) and child.node_type == "binding":
                bindings.append(self._convert_binding(child))

        return bindings

    def _extract_let_result(self, node: CstContainer) -> Optional[NixObject]:
        """Extract the result expression from a let-in."""
        # The result is typically the last non-binding, non-trivia child
        children = [c for c in node.children if not isinstance(c, CstVerbatim)]

        for child in reversed(children):
            if not (isinstance(child, CstNixBinding) or
                    (isinstance(child, CstElement) and child.node_type == "binding")):
                return self._convert_node(child)

        return None

    def _convert_attr_set_from_element(self, node: CstElement) -> NixAttributeSet:
        """Convert an attr_set element to NixAttributeSet."""
        bindings = []

        for child in node.children:
            if isinstance(child, CstNixBinding):
                bindings.append(self._convert_binding(child))
            elif isinstance(child, CstElement) and child.node_type == "binding":
                bindings.append(self._convert_binding(child))

        attr_set = NixAttributeSet(values=bindings)
        attr_set.before = self.trivia_processor.extract_trivia(node)

        return attr_set

    def _convert_attr_set(self, node: NixAttrSet) -> NixAttributeSet:
        """Convert a NixAttrSet container to NixAttributeSet."""
        bindings = []

        for child in node.children:
            if isinstance(child, CstNixBinding):
                bindings.append(self._convert_binding(child))
            elif isinstance(child, CstElement) and child.node_type == "binding":
                bindings.append(self._convert_binding(child))

        attr_set = NixAttributeSet(values=bindings)
        attr_set.before = self.trivia_processor.extract_trivia(node)

        return attr_set

    def _convert_binding(self, node: Union[CstNixBinding, CstElement]) -> NixBinding:
        """Convert a binding to NixBinding."""
        name = ""
        value = None

        if isinstance(node, CstNixBinding):
            children = node.children
        else:
            children = node.children

        # Extract name and value from children
        for i, child in enumerate(children):
            if isinstance(child, CstNixIdentifier):
                name = child.text.strip()
            elif isinstance(child, CstElement) and child.node_type == "identifier":
                name = self._convert_identifier(child).name
            elif isinstance(child, CstElement) and child.node_type == "attrpath":
                # Handle dotted attribute paths
                path_parts = []
                for grandchild in child.children:
                    if isinstance(grandchild, CstNixIdentifier):
                        path_parts.append(grandchild.text.strip())
                    elif isinstance(grandchild, CstElement) and grandchild.node_type == "identifier":
                        path_parts.append(self._convert_identifier(grandchild).name)
                name = ".".join(path_parts)
            elif not isinstance(child, CstVerbatim) and name:  # This is likely the value
                value = self._convert_node(child)

        if value is None:
            value = ""

        binding = NixBinding(name=name, value=value)

        # Extract before trivia
        if isinstance(node, CstContainer):
            binding.before = self.trivia_processor.extract_before_trivia(
                node.parent if hasattr(node, 'parent') else node, 0)

        binding.after = self.trivia_processor.extract_trivia(node)

        return binding

    def _convert_identifier(self, node: Union[CstNixIdentifier, CstElement]) -> NixIdentifier:
        """Convert an identifier to NixIdentifier."""
        if isinstance(node, CstNixIdentifier):
            name = node.text.strip()
        else:
            name = ""
            for child in node.children:
                if isinstance(child, CstLeaf):
                    name += child.text
            name = name.strip()

        identifier = NixIdentifier(name=name)
        identifier.before = self.trivia_processor.extract_trivia(node)

        return identifier

    def _convert_function_call(self, node: CstElement) -> FunctionCall:
        """Convert an application (function call) to FunctionCall."""
        function_name = ""
        argument = None

        # The first child is usually the function name, subsequent ones are arguments
        children = [c for c in node.children if not isinstance(c, CstVerbatim)]

        if children:
            # Extract function name
            first_child = children[0]
            if isinstance(first_child, CstNixIdentifier):
                function_name = first_child.text.strip()
            elif isinstance(first_child, CstElement) and first_child.node_type == "identifier":
                function_name = self._convert_identifier(first_child).name
            elif isinstance(first_child, CstElement) and first_child.node_type == "select_expression":
                function_name = self._extract_select_expression_name(first_child)

            # Extract arguments
            if len(children) > 1:
                arg_child = children[1]
                if isinstance(arg_child, NixAttrSet) or (
                        isinstance(arg_child, CstElement) and arg_child.node_type == "attr_set"):
                    argument = self._convert_node(arg_child)

        function_call = FunctionCall(name=function_name, argument=argument)
        function_call.before = self.trivia_processor.extract_trivia(node)

        return function_call

    def _extract_select_expression_name(self, node: CstElement) -> str:
        """Extract the full name from a select expression (e.g., 'lib.maintainers.hoh')."""
        parts = []

        def extract_parts(n):
            if isinstance(n, CstNixIdentifier):
                parts.append(n.text.strip())
            elif isinstance(n, CstElement) and n.node_type == "identifier":
                for child in n.children:
                    if isinstance(child, CstLeaf):
                        parts.append(child.text.strip())
            elif isinstance(n, CstElement):
                for child in n.children:
                    if not isinstance(child, CstVerbatim):
                        extract_parts(child)

        extract_parts(node)
        return ".".join(parts)

    def _convert_list(self, node: CstElement) -> NixList:
        """Convert a list element to NixList."""
        items = []

        for child in node.children:
            if not isinstance(child, CstVerbatim):
                converted = self._convert_node(child)
                if isinstance(converted, NixIdentifier):
                    items.append(converted.name)
                elif isinstance(converted, str):
                    items.append(converted)
                else:
                    items.append(converted)

        nix_list = NixList(value=items)
        nix_list.before = self.trivia_processor.extract_trivia(node)

        return nix_list

    def _convert_with(self, node: CstElement) -> NixWith:
        """Convert a with expression to NixWith."""
        expression = None
        attributes = []

        children = [c for c in node.children if not isinstance(c, CstVerbatim)]

        # First non-trivia child after 'with' keyword is the expression
        if len(children) >= 1:
            expr_child = children[0]
            if isinstance(expr_child, CstNixIdentifier):
                expression = NixIdentifier(name=expr_child.text.strip())
            elif isinstance(expr_child, CstElement):
                if expr_child.node_type == "identifier":
                    expression = self._convert_identifier(expr_child)
                elif expr_child.node_type == "select_expression":
                    name = self._extract_select_expression_name(expr_child)
                    expression = NixIdentifier(name=name)

        # The body is usually a list or other expression containing the attributes
        if len(children) >= 2:
            body_child = children[1]
            if isinstance(body_child, CstElement) and body_child.node_type == "list":
                # Extract identifiers from the list
                for list_child in body_child.children:
                    if isinstance(list_child, CstNixIdentifier):
                        attributes.append(NixIdentifier(name=list_child.text.strip()))
                    elif isinstance(list_child, CstElement) and list_child.node_type == "identifier":
                        attributes.append(self._convert_identifier(list_child))

        nix_with = NixWith(expression=expression, attributes=attributes)
        nix_with.before = self.trivia_processor.extract_trivia(node)

        return nix_with

    def _convert_string_value(self, node: Union[NixString, CstElement]) -> str:
        """Convert a string node to its string value."""
        if isinstance(node, NixString):
            text = node.text
        else:
            text = ""
            for child in node.children:
                if isinstance(child, CstLeaf):
                    text += child.text

        # Remove quotes
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.startswith("''") and text.endswith("''"):
            return text[2:-2]

        return text.strip()

    def _convert_leaf_value(self, node: CstLeaf) -> Union[str, int, bool]:
        """Convert a leaf node to its appropriate Python value."""
        text = node.text.strip()

        # Handle different literal types
        if text == "true":
            return True
        elif text == "false":
            return False
        elif text.isdigit():
            return int(text)
        elif text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.startswith("''") and text.endswith("''"):
            return text[2:-2]
        else:
            return text

    def _convert_generic(self, node: CstNode) -> NixExpression:
        """Generic conversion for unspecialized nodes."""
        if isinstance(node, CstLeaf):
            value = self._convert_leaf_value(node)
        else:
            # For containers, try to extract a meaningful value
            value = ""
            if isinstance(node, CstContainer):
                for child in node.children:
                    if isinstance(child, CstLeaf):
                        value += child.text

        expression = NixExpression(value=value)
        expression.before = self.trivia_processor.extract_trivia(node)

        return expression

    def _find_child_by_type(self, node: CstContainer, node_type: str) -> Optional[CstElement]:
        """Find a child element by its node type."""
        for child in node.children:
            if isinstance(child, CstElement) and child.node_type == node_type:
                return child
        return None


# High-level conversion functions

def convert_nix_source(source_code: bytes) -> NixObject:
    """Convert Nix source code to high-level symbol objects."""
    cst_root = parse_nix_cst(source_code)
    converter = CstToSymbolConverter()
    return converter.convert(cst_root)


def convert_nix_file(file_path) -> Optional[NixObject]:
    """Convert a Nix file to high-level symbol objects."""
    from pathlib import Path

    try:
        file_path = Path(file_path)
        source_code = file_path.read_bytes()
        return convert_nix_source(source_code)
    except Exception as e:
        print(f"Error converting file {file_path}: {e}")
        return None


# Example usage and pretty printing

def pretty_print_symbols(obj: NixObject, indent_level=0) -> str:
    """Generate a nicely formatted string representation of symbol objects."""
    indent = '  ' * indent_level

    if isinstance(obj, FunctionDefinition):
        parts = [f"{indent}FunctionDefinition("]
        if obj.recursive:
            parts.append(f"{indent}  recursive=True,")
        if obj.argument_set:
            parts.append(f"{indent}  argument_set=[")
            for arg in obj.argument_set:
                parts.append(pretty_print_symbols(arg, indent_level + 2) + ",")
            parts.append(f"{indent}  ],")
        if obj.let_statements:
            parts.append(f"{indent}  let_statements=[")
            for stmt in obj.let_statements:
                parts.append(pretty_print_symbols(stmt, indent_level + 2) + ",")
            parts.append(f"{indent}  ],")
        if obj.result:
            parts.append(f"{indent}  result=")
            parts.append(pretty_print_symbols(obj.result, indent_level + 1))
        parts.append(f"{indent})")
        return '\n'.join(parts)

    elif isinstance(obj, NixAttributeSet):
        parts = [f"{indent}NixAttributeSet(values=["]
        for binding in obj.values:
            parts.append(pretty_print_symbols(binding, indent_level + 1) + ",")
        parts.append(f"{indent}])")
        return '\n'.join(parts)

    elif isinstance(obj, NixBinding):
        value_str = pretty_print_symbols(obj.value, indent_level + 1) if isinstance(obj.value, NixObject) else repr(
            obj.value)
        return f"{indent}NixBinding(name={obj.name!r}, value={value_str})"

    elif isinstance(obj, NixIdentifier):
        return f"{indent}NixIdentifier(name={obj.name!r})"

    elif isinstance(obj, FunctionCall):
        parts = [f"{indent}FunctionCall(name={obj.name!r}"]
        if obj.argument:
            parts.append(f", argument=")
            parts.append(pretty_print_symbols(obj.argument, indent_level + 1))
        parts.append(")")
        return ''.join(parts)

    elif isinstance(obj, NixList):
        return f"{indent}NixList(value={obj.value!r})"

    elif isinstance(obj, NixWith):
        expr_str = pretty_print_symbols(obj.expression, 0) if obj.expression else "None"
        attrs_str = [attr.name for attr in obj.attributes]
        return f"{indent}NixWith(expression={expr_str}, attributes={attrs_str!r})"

    elif isinstance(obj, (Comment, MultilineComment)):
        return f"{indent}{obj.__class__.__name__}(text={obj.text!r})"

    else:
        return f"{indent}{obj.__class__.__name__}({obj.__dict__})"


def main():
    """Example usage with pretty printing."""
    import argparse
    from pathlib import Path
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers.python import PythonLexer
    from pygments.lexers.nix import NixLexer

    parser = argparse.ArgumentParser(
        description="Convert a Nix file to high-level symbol objects and display the result."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    args = parser.parse_args()

    # Convert the file
    symbol_obj = convert_nix_file(Path(args.file))

    if not symbol_obj:
        return

    print("--- High-Level Symbol Objects ---")
    symbol_string = pretty_print_symbols(symbol_obj)
    print(highlight(symbol_string, PythonLexer(), TerminalFormatter()))

    print("\n--- Reconstructed Nix Code ---")
    rebuilt_code = symbol_obj.rebuild()
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))


if __name__ == "__main__":
    main()