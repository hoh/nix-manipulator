from __future__ import annotations
from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions import NixExpression


class Parenthesis(NixExpression):
    tree_sitter_types: ClassVar[set[str]] = {"parenthesized_expression"}
    value: NixExpression

    @classmethod
    def from_cst(cls, node: Node) -> Parenthesis:
        print(node.children)
        children_types = [child.type for child in node.children]

        assert children_types[:3] == ["let", "binding_set", "in"], f"Invalid let expression {children_types}"
