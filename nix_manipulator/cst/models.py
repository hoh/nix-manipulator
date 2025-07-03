from __future__ import annotations

from tree_sitter import Node

from nix_manipulator.symbols import (
    NixExpression,
    NixList,
    FunctionCall,
    Comment,
    FunctionDefinition,
)


class NixSourceCode:
    def __init__(self, node, value):
        self.node = node
        self.value = value

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.cst.parser import parse_to_cst

        value = [parse_to_cst(obj) for obj in node.children]
        return cls(node, value)

    def rebuild(self):
        return "".join(obj.rebuild() for obj in self.value)

    def __repr__(self):
        return f"NixSourceCode(\n  node={self.node}, \n  value={self.value}\n)"


NODE_TYPE_TO_CLASS = {
    # "comment": NixComment,
    # "identifier": NixIdentifier,
    # "string_expression": NixString,
    # "indented_string_expression": NixString,
    # "binding": NixBinding,
    # "attr_set": NixAttrSet,
    # "let_in": NixLetIn,
    # "lambda": NixLambda,
    # "formal": NixFormal,
    "list_expression": NixList,
    "integer_expression": NixExpression,
    "source_code": NixSourceCode,
    "apply_expression": FunctionCall,
    "comment": Comment,
    "string_expression": NixExpression,
    "function_expression": FunctionDefinition,
    "variable_expression": NixExpression,
}
