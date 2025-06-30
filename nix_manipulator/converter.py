# CST nodes from parser.py to symbols in symbols.py

from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
from collections import OrderedDict
import re

from .parser import (
    CstNode, CstContainer, CstLeaf, CstElement, CstVerbatim,
    NixComment, NixIdentifier as CstNixIdentifier, NixString, NixBinding as CstNixBinding,
    NixAttrSet, NixLetIn, NixLambda, NixFormal, parse_nix_cst
)
from .symbols import (
    NixObject, FunctionDefinition, NixIdentifier, Comment, MultilineComment,
    NixBinding, NixSet, FunctionCall, NixExpression, NixList, NixWith,
    empty_line, linebreak, comma
)


class TriviaProcessor:
    """Processes trivia (whitespace, comments) from CST nodes."""

    @staticmethod
    def extract_trivia(cst_node: CstNode) -> List[Any]:
        """Extract trivia from a CST node's post_trivia."""
        trivia = []

        for trivia_node in cst_node.post_trivia:
            if isinstance(trivia_node, NixComment):
                text = trivia_node.text.strip()
                if text.startswith('/*') and text.endswith('*/'):
                    # Multiline comment
                    content = text[2:-2].strip()
                    trivia.append(MultilineComment(text=content))
                elif text.startswith('#'):
                    # Single line comment
                    content = text[1:].strip()
                    trivia.append(Comment(text=content))
            elif isinstance(trivia_node, CstVerbatim):
                text = trivia_node.text
                if '\n\n' in text or text.count('\n') > 1:
                    trivia.append(empty_line)
                elif '\n' in text:
                    trivia.append(linebreak)
                elif ',' in text:
                    trivia.append(comma)

        return trivia


class CstToSymbolConverter:
    """Converts CST nodes to high-level symbol objects."""

    def __init__(self):
        self.trivia_processor = TriviaProcessor()

    def convert(self, cst_node: CstNode) -> NixObject:
        """Main conversion entry point."""
        return self._convert_node(cst_node)

    def _convert_node(self, node: CstNode) -> Any:
        """Convert a single CST node to a symbol object."""
        if isinstance(node, CstElement):
            if node.node_type == "lambda":
                return self._convert_lambda(node)
            elif node.node_type == "let_in":
                return self._convert_let_in(node)
            elif node.node_type == "apply":
                return self._convert_function_call(node)
            elif node.node_type == "list":
                return self._convert_list(node)
            elif node.node_type == "with":
                return self._convert_with(node)
        elif isinstance(node, NixAttrSet):
            return self._convert_attr_set(node)
        elif isinstance(node, CstNixBinding):
            return self._convert_binding(node)
        elif isinstance(node, CstNixIdentifier):
            return self._convert_identifier(node)
        elif isinstance(node, NixString):
            return self._convert_string_value(node)
        elif isinstance(node, CstLeaf):
            return self._convert_leaf_value(node)

        # Fallback for unknown nodes
        return self._convert_generic(node)

    def _convert_lambda(self, node: CstElement) -> FunctionDefinition:
        """Convert a lambda expression to a FunctionDefinition."""
        # Extract formal parameters
        argument_set = []
        let_statements = []
        result = None
        recursive = False
        name = "anonymous"

        # Find formals (parameters)
        formals_node = self._find_child_by_type(node, "formals")
        if formals_node:
            for child in formals_node.children:
                if isinstance(child, NixFormal) and child.identifier:
                    arg_name = child.identifier.text
                    trivia = self.trivia_processor.extract_trivia(child)
                    argument_set.append(NixIdentifier(name=arg_name, before=trivia))

        # Find body
        body_nodes = [child for child in node.children if not isinstance(child, CstLeaf)]
        if body_nodes:
            last_node = body_nodes[-1]
            if isinstance(last_node, NixLetIn):
                # Extract let bindings and result
                let_statements = self._extract_let_bindings(last_node)
                result = self._extract_let_result(last_node)
            else:
                result = self._convert_node(last_node)

        trivia = self.trivia_processor.extract_trivia(node)

        return FunctionDefinition(
            name=name,
            recursive=recursive,
            argument_set=argument_set,
            let_statements=let_statements,
            result=result or NixSet(values={}),
            after=trivia
        )

    def _convert_let_in(self, node: CstElement) -> Dict[str, Any]:
        """Convert let-in expression, returning bindings and result separately."""
        bindings = []
        result = None

        # Find all bindings in the let section
        for child in node.children:
            if isinstance(child, CstNixBinding):
                binding = self._convert_binding(child)
                bindings.append(binding)
            elif not isinstance(child, CstLeaf):
                # This might be the result expression
                result = self._convert_node(child)

        return {"bindings": bindings, "result": result}

    def _extract_let_bindings(self, let_node: CstElement) -> List[NixBinding]:
        """Extract bindings from let-in node."""
        let_data = self._convert_let_in(let_node)
        return let_data.get("bindings", [])

    def _extract_let_result(self, let_node: CstElement) -> Any:
        """Extract result from let-in node."""
        let_data = self._convert_let_in(let_node)
        return let_data.get("result")

    def _convert_attr_set(self, node: NixAttrSet) -> NixSet:
        """Convert attribute set to NixSet."""
        values = OrderedDict()

        for child in node.children:
            if isinstance(child, CstNixBinding):
                binding = self._convert_binding(child)
                values[binding.name] = binding.value

        trivia = self.trivia_processor.extract_trivia(node)

        return NixSet(values=values, before=trivia)

    def _convert_binding(self, node: CstNixBinding) -> NixBinding:
        """Convert a binding node to NixBinding."""
        name = ""
        value = None

        # Extract name and value from binding
        for child in node.children:
            if isinstance(child, CstNixIdentifier):
                name = child.text
            elif isinstance(child, CstLeaf) and child.text not in ['=', ';']:
                value = self._convert_leaf_value(child)
            elif not isinstance(child, CstLeaf):
                value = self._convert_node(child)

        trivia = self.trivia_processor.extract_trivia(node)

        return NixBinding(name=name, value=value, before=trivia)

    def _convert_identifier(self, node: CstNixIdentifier) -> NixIdentifier:
        """Convert identifier to NixIdentifier."""
        trivia = self.trivia_processor.extract_trivia(node)
        return NixIdentifier(name=node.text, after=trivia)

    def _convert_function_call(self, node: CstElement) -> FunctionCall:
        """Convert function application to FunctionCall."""
        name = ""
        arguments = []

        # First child is usually the function name
        if node.children:
            func_node = node.children[0]
            if isinstance(func_node, CstNixIdentifier):
                name = func_node.text

            # Rest are arguments
            for child in node.children[1:]:
                if isinstance(child, NixAttrSet):
                    # Convert attribute set arguments to bindings
                    attr_set = self._convert_attr_set(child)
                    for key, value in attr_set.values.items():
                        arguments.append(NixBinding(name=key, value=value))

        trivia = self.trivia_processor.extract_trivia(node)

        return FunctionCall(name=name, arguments=arguments, before=trivia)

    def _convert_list(self, node: CstElement) -> NixList:
        """Convert list to NixList."""
        values = []

        for child in node.children:
            if not isinstance(child, CstLeaf) or child.text not in ['[', ']']:
                values.append(self._convert_node(child))

        trivia = self.trivia_processor.extract_trivia(node)

        return NixList(value=values, before=trivia)

    def _convert_with(self, node: CstElement) -> NixWith:
        """Convert with expression to NixWith."""
        expression = None
        attributes = []

        # Extract expression and attributes
        for child in node.children:
            if isinstance(child, CstNixIdentifier):
                if expression is None:
                    expression = NixIdentifier(name=child.text)
                else:
                    attributes.append(NixIdentifier(name=child.text))

        return NixWith(expression=expression, attributes=attributes)

    def _convert_string_value(self, node: NixString) -> str:
        """Convert string node to string value."""
        text = node.text
        # Remove quotes if present
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.startswith("''") and text.endswith("''"):
            return text[2:-2]
        return text

    def _convert_leaf_value(self, node: CstLeaf) -> Union[str, int, bool]:
        """Convert leaf node to appropriate Python value."""
        text = node.text.strip()

        # Try to parse as different types
        if text.lower() == 'true':
            return True
        elif text.lower() == 'false':
            return False
        elif text.isdigit():
            return int(text)
        elif text.startswith('"') and text.endswith('"'):
            return text[1:-1]  # Remove quotes
        else:
            return text

    def _convert_generic(self, node: CstNode) -> NixExpression:
        """Generic conversion for unknown nodes."""
        if isinstance(node, CstLeaf):
            value = self._convert_leaf_value(node)
        else:
            value = str(node)

        trivia = self.trivia_processor.extract_trivia(node)

        return NixExpression(value=value, before=trivia)

    def _find_child_by_type(self, node: CstContainer, node_type: str) -> Optional[CstNode]:
        """Find a child node by its type."""
        for child in node.children:
            if isinstance(child, CstElement) and child.node_type == node_type:
                return child
        return None


def convert_nix_source(source_code: str) -> NixObject:
    """Convert Nix source code to high-level symbol objects."""
    # Parse to CST first
    cst_root = parse_nix_cst(source_code.encode('utf-8'))

    # Convert CST to symbols
    converter = CstToSymbolConverter()
    return converter.convert(cst_root)


def convert_nix_file(file_path: str) -> Optional[NixObject]:
    """Convert a Nix file to high-level symbol objects."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        return convert_nix_source(source_code)
    except Exception as e:
        print(f"Error converting file {file_path}: {e}")
        return None