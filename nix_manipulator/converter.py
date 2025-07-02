from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from .parser import (
    CstNode,
    CstContainer,
    CstLeaf,
    CstElement,
    CstVerbatim,
    NixComment,
    NixIdentifier as CstNixIdentifier,
    NixString,
    NixBinding as CstNixBinding,
    NixAttrSet,
    NixLetIn,
    NixLambda,
    NixFormal,
    parse_nix_cst,
)
from .symbols import (
    NixObject,
    FunctionDefinition,
    NixIdentifier,
    Comment,
    MultilineComment,
    NixBinding,
    NixAttributeSet,
    FunctionCall,
    NixExpression,
    NixList,
    NixWith,
    empty_line,
    comma,
)


class TriviaProcessor:
    """Processes trivia (whitespace, comments) from CST nodes."""

    @staticmethod
    def extract_trivia(cst_node: CstNode) -> List[Any]:
        """Extract trivia from a CST node's post_trivia."""
        trivia = []

        # Check if the node has post_trivia attribute
        if not hasattr(cst_node, "post_trivia"):
            return trivia

        for trivia_node in cst_node.post_trivia:
            if isinstance(trivia_node, NixComment):
                text = trivia_node.text.strip()
                if text.startswith("/*") and text.endswith("*/"):
                    # Multiline comment - extract content between /* and */
                    content = text[2:-2]
                    trivia.append(MultilineComment(text=content))
                elif text.startswith("#"):
                    # Single line comment - extract content after #
                    content = text[1:].strip()
                    trivia.append(Comment(text=content))
            elif isinstance(trivia_node, CstVerbatim):
                text = trivia_node.text
                if "\n\n" in text or text.count("\n") > 1:
                    trivia.append(empty_line)
                elif "," in text:
                    trivia.append(comma)

        return trivia

    @staticmethod
    def extract_before_trivia(cst_node: CstNode) -> List[Any]:
        """Extract trivia that comes before a node."""
        trivia = []

        # Check if the node has pre_trivia or similar attribute
        if hasattr(cst_node, "pre_trivia"):
            for trivia_node in cst_node.pre_trivia:
                if isinstance(trivia_node, NixComment):
                    text = trivia_node.text.strip()
                    if text.startswith("/*") and text.endswith("*/"):
                        content = text[2:-2]
                        trivia.append(MultilineComment(text=content))
                    elif text.startswith("#"):
                        content = text[1:].strip()
                        trivia.append(Comment(text=content))
                elif isinstance(trivia_node, CstVerbatim):
                    text = trivia_node.text
                    if "\n\n" in text or text.count("\n") > 1:
                        trivia.append(empty_line)

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
            # Handle different node types
            if node.node_type == "source_code":
                return self._convert_source_code(node)
            elif node.node_type == "function_expression":
                return self._convert_lambda(node)
            elif node.node_type == "let_expression":
                return self._convert_let_in(node)
            elif node.node_type == "apply_expression":
                return self._convert_function_call(node)
            elif node.node_type == "list_expression":
                return self._convert_list(node)
            elif node.node_type == "with_expression":
                return self._convert_with(node)
            elif node.node_type in ["attrset_expression", "rec_attrset_expression"]:
                return self._convert_attr_set_from_element(node)
            elif node.node_type == "parenthesized_expression":
                return self._convert_parenthesized(node)
            elif node.node_type == "select_expression":
                return self._convert_select_expression(node)
            elif node.node_type in ["string_expression", "indented_string_expression"]:
                return self._convert_string_from_element(node)
            elif node.node_type == "variable_expression":
                return self._convert_variable_expression(node)
        elif isinstance(node, NixAttrSet):
            return self._convert_attr_set(node)
        elif isinstance(node, CstNixBinding):
            return self._convert_binding(node)
        elif isinstance(node, CstNixIdentifier):
            return self._convert_identifier(node)
        elif isinstance(node, NixString):
            return self._convert_string_value(node)
        elif isinstance(node, NixLambda):
            return self._convert_lambda_container(node)
        elif isinstance(node, CstLeaf):
            return self._convert_leaf_value(node)

        # Fallback for unknown nodes
        return self._convert_generic(node)

    def _convert_variable_expression(self, node: CstElement) -> NixIdentifier:
        """Convert variable expression to NixIdentifier."""
        # Extract the identifier name from the variable expression
        name = ""
        for child in node.children:
            if isinstance(child, CstLeaf):
                name = child.text
                break

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return NixIdentifier(name=name, before=before_trivia, after=after_trivia)

    def _convert_source_code(self, node: CstElement) -> NixObject:
        """Convert the root source_code node by finding the main expression."""
        # Find the first non-trivia child
        for child in node.children:
            if not isinstance(child, CstVerbatim):
                return self._convert_node(child)

        # Fallback to empty set if nothing found
        return NixAttributeSet(values=[])

    def _convert_parenthesized(self, node: CstElement) -> NixObject:
        """Convert parenthesized expression by extracting the inner content."""
        # Find the expression inside parentheses
        for child in node.children:
            if not isinstance(child, CstLeaf) and not isinstance(child, CstVerbatim):
                return self._convert_node(child)

        return NixExpression(value="")

    def _convert_select_expression(self, node: CstElement) -> NixIdentifier:
        """Convert select expression (like lib.maintainers) to NixIdentifier."""
        name = self._extract_select_expression_name(node)
        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)
        return NixIdentifier(name=name, before=before_trivia, after=after_trivia)

    def _convert_string_from_element(self, node: CstElement) -> str:
        """Convert string element to string value."""
        # Extract the actual string content
        text = ""
        for child in node.children:
            if isinstance(child, CstLeaf):
                text += child.text

        # Remove quotes if present
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.startswith("''") and text.endswith("''"):
            return text[2:-2]
        return text

    def _convert_lambda_container(self, node: NixLambda) -> FunctionDefinition:
        """Convert a NixLambda container to FunctionDefinition."""
        argument_set = []
        let_statements = []
        result = None
        recursive = False

        # Extract formals and body from lambda container
        formals_found = False
        body_node = None

        for child in node.children:
            if isinstance(child, CstElement):
                if child.node_type == "formals":
                    formals_found = True
                    # Extract formal parameters
                    for formal_child in child.children:
                        if isinstance(formal_child, NixFormal):
                            if formal_child.identifier:
                                arg_name = formal_child.identifier.text
                                before_trivia = (
                                    self.trivia_processor.extract_before_trivia(
                                        formal_child
                                    )
                                )
                                after_trivia = self.trivia_processor.extract_trivia(
                                    formal_child
                                )
                                argument_set.append(
                                    NixIdentifier(
                                        name=arg_name,
                                        before=before_trivia,
                                        after=after_trivia,
                                    )
                                )
                elif not formals_found or child.node_type not in [":", "formals"]:
                    # This might be the body
                    body_node = child

        # Convert body
        if body_node:
            if isinstance(body_node, NixLetIn) or (
                isinstance(body_node, CstElement)
                and body_node.node_type == "let_expression"
            ):
                let_data = self._convert_let_in(body_node)
                let_statements = let_data.get("bindings", [])
                result = let_data.get("result")
            else:
                result = self._convert_node(body_node)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return FunctionDefinition(
            recursive=recursive,
            argument_set=argument_set,
            let_statements=let_statements,
            result=result or NixAttributeSet(values=[]),
            before=before_trivia,
            after=after_trivia,
        )

    def _convert_lambda(self, node: CstElement) -> FunctionDefinition:
        """Convert a lambda expression to a FunctionDefinition."""
        argument_set = []
        let_statements = []
        result = None
        recursive = False

        # Find formals (parameters) and body
        formals_node = None
        body_node = None

        for child in node.children:
            if isinstance(child, CstElement):
                if child.node_type == "formals":
                    formals_node = child
                elif child.node_type not in [":", "formals"] and body_node is None:
                    body_node = child

        # Extract formal parameters
        if formals_node:
            for child in formals_node.children:
                if isinstance(child, NixFormal) and child.identifier:
                    arg_name = child.identifier.text
                    before_trivia = self.trivia_processor.extract_before_trivia(child)
                    after_trivia = self.trivia_processor.extract_trivia(child)
                    argument_set.append(
                        NixIdentifier(
                            name=arg_name, before=before_trivia, after=after_trivia
                        )
                    )

        # Convert body
        if body_node:
            if body_node.node_type == "let_expression":
                let_data = self._convert_let_in(body_node)
                let_statements = let_data.get("bindings", [])
                result = let_data.get("result")
            else:
                result = self._convert_node(body_node)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return FunctionDefinition(
            recursive=recursive,
            argument_set=argument_set,
            let_statements=let_statements,
            result=result or NixAttributeSet(values=[]),
            before=before_trivia,
            after=after_trivia,
        )

    def _convert_let_in(self, node: CstElement) -> Dict[str, Any]:
        """Convert let-in expression, returning bindings and result separately."""
        bindings = []
        result = None

        # Look for binding_set and the result expression
        for child in node.children:
            if isinstance(child, CstElement):
                if child.node_type == "binding_set":
                    # Extract bindings from binding_set
                    for binding_child in child.children:
                        if isinstance(binding_child, CstNixBinding):
                            binding = self._convert_binding(binding_child)
                            bindings.append(binding)
                elif child.node_type not in ["let", "in", "binding_set"]:
                    # This should be the result expression
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

    def _convert_attr_set_from_element(self, node: CstElement) -> NixAttributeSet:
        """Convert CstElement attrset to NixAttributeSet."""
        bindings = []
        recursive = node.node_type == "rec_attrset_expression"

        # Look for binding_set
        for child in node.children:
            if isinstance(child, CstElement) and child.node_type == "binding_set":
                for binding_child in child.children:
                    if isinstance(binding_child, CstNixBinding):
                        binding = self._convert_binding(binding_child)
                        bindings.append(binding)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)
        return NixAttributeSet(
            values=bindings,
            recursive=recursive,
            before=before_trivia,
            after=after_trivia,
        )

    def _convert_attr_set(self, node: NixAttrSet) -> NixAttributeSet:
        """Convert attribute set to NixAttributeSet."""
        bindings = []

        for child in node.children:
            if isinstance(child, CstNixBinding):
                binding = self._convert_binding(child)
                bindings.append(binding)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return NixAttributeSet(
            values=bindings, before=before_trivia, after=after_trivia
        )

    def _convert_binding(self, node: CstNixBinding) -> NixBinding:
        """Convert a binding node to NixBinding."""
        name = ""
        value = None

        # Look for attrpath and expression
        for child in node.children:
            if isinstance(child, CstElement):
                if child.node_type == "attrpath":
                    # Extract identifier from attrpath
                    for path_child in child.children:
                        if isinstance(path_child, CstNixIdentifier):
                            name = path_child.text
                            break
                        elif isinstance(path_child, CstLeaf):
                            name = path_child.text
                            break
                elif child.node_type not in ["=", ";"]:
                    # This should be the value expression
                    value = self._convert_node(child)
            elif isinstance(child, CstNixIdentifier):
                if not name:  # Only use as name if we haven't found one yet
                    name = child.text
                else:
                    value = self._convert_identifier(child)
            elif isinstance(child, CstLeaf):
                if child.text not in ["=", ";"]:
                    if not name:
                        name = child.text
                    else:
                        value = self._convert_leaf_value(child)
            elif not isinstance(child, CstVerbatim):
                if value is None:
                    value = self._convert_node(child)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return NixBinding(
            name=name, value=value or "", before=before_trivia, after=after_trivia
        )

    def _convert_identifier(self, node: CstNixIdentifier) -> NixIdentifier:
        """Convert identifier to NixIdentifier."""
        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)
        return NixIdentifier(name=node.text, before=before_trivia, after=after_trivia)

    def _convert_function_call(self, node: CstElement) -> FunctionCall:
        """Convert function application to FunctionCall."""
        name = ""
        argument = None
        recursive = False

        function_node = None
        argument_node = None

        # Find function and argument
        for child in node.children:
            if isinstance(child, CstNixIdentifier):
                if not function_node:
                    function_node = child
                    name = child.text
            elif isinstance(child, CstElement):
                if child.node_type == "select_expression":
                    # Handle something like stdenv.mkDerivation
                    if not function_node:
                        function_node = child
                        name = self._extract_select_expression_name(child)
                elif not argument_node and child.node_type in [
                    "attrset_expression",
                    "rec_attrset_expression",
                ]:
                    argument_node = child
                    if child.node_type == "rec_attrset_expression":
                        recursive = True

        # Convert argument
        if argument_node:
            argument = self._convert_attr_set_from_element(argument_node)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return FunctionCall(
            name=name,
            argument=argument,
            recursive=recursive,
            before=before_trivia,
            after=after_trivia,
        )

    def _extract_select_expression_name(self, node: CstElement) -> str:
        """Extract name from select expression like stdenv.mkDerivation."""
        parts = []

        def extract_parts(n):
            if isinstance(n, CstNixIdentifier):
                parts.append(n.text)
            elif isinstance(n, CstLeaf):
                if n.text not in [".", "(", ")"]:
                    parts.append(n.text)
            elif isinstance(n, CstElement):
                for child in n.children:
                    extract_parts(child)

        extract_parts(node)
        return ".".join(parts)

    def _convert_list(self, node: CstElement) -> NixList:
        """Convert list to NixList."""
        values = []
        multiline = False

        # Check if list spans multiple lines
        for child in node.children:
            if isinstance(child, CstVerbatim) and "\n" in child.text:
                multiline = True
                break

        for child in node.children:
            if not isinstance(child, CstLeaf) or child.text not in ["[", "]"]:
                if not isinstance(child, CstVerbatim):  # Skip whitespace
                    converted = self._convert_node(child)
                    if converted is not None:
                        values.append(converted)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return NixList(
            value=values, multiline=multiline, before=before_trivia, after=after_trivia
        )

    def _convert_with(self, node: CstElement) -> NixWith:
        """Convert with expression to NixWith."""
        expression = None
        attributes = []

        # The with expression structure is typically: with <expr>; <body>
        # We need to handle this more carefully
        found_semicolon = False

        for child in node.children:
            if isinstance(child, CstLeaf) and child.text == ";":
                found_semicolon = True
                continue
            elif isinstance(child, CstLeaf) and child.text == "with":
                continue
            elif isinstance(child, CstVerbatim):
                continue

            if isinstance(child, CstNixIdentifier):
                if not found_semicolon and expression is None:
                    expression = NixIdentifier(name=child.text)
                elif found_semicolon:
                    attributes.append(NixIdentifier(name=child.text))
            elif isinstance(child, CstElement):
                if child.node_type == "select_expression" and expression is None:
                    # This is the expression part like lib.maintainers
                    name = self._extract_select_expression_name(child)
                    expression = NixIdentifier(name=name)
                elif found_semicolon:
                    # This is part of the body - could be a list expression
                    if child.node_type == "list_expression":
                        list_result = self._convert_list(child)
                        if isinstance(list_result, NixList):
                            for item in list_result.value:
                                if isinstance(item, NixIdentifier):
                                    attributes.append(item)

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)
        return NixWith(
            expression=expression,
            attributes=attributes,
            before=before_trivia,
            after=after_trivia,
        )

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
        if text.lower() == "true":
            return NixExpression(value=True)
        elif text.lower() == "false":
            return NixExpression(value=False)
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

        before_trivia = self.trivia_processor.extract_before_trivia(node)
        after_trivia = self.trivia_processor.extract_trivia(node)

        return NixExpression(value=value, before=before_trivia, after=after_trivia)

    def _find_child_by_type(
        self, node: CstContainer, node_type: str
    ) -> Optional[CstNode]:
        """Find a child node by its type."""
        for child in node.children:
            if isinstance(child, CstElement) and child.node_type == node_type:
                return child
        return None


def convert_nix_source(source_code: str) -> NixObject:
    """Convert Nix source code to high-level symbol objects."""
    # Parse to CST first
    cst_root = parse_nix_cst(source_code.encode("utf-8"))

    # Convert CST to symbols
    converter = CstToSymbolConverter()
    return converter.convert(cst_root)


def convert_nix_file(file_path: Path) -> Optional[NixObject]:
    """Convert a Nix file to high-level symbol objects."""
    try:
        source_code = file_path.read_text()
        return convert_nix_source(source_code)
    except Exception as e:
        print(f"Error converting file {file_path}: {e}")
        return None
