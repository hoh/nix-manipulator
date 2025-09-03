from __future__ import annotations

from typing import Any, List, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.layout import empty_line


class Assertion(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "assert_expression",
    }
    expression: NixExpression

    @classmethod
    def from_cst(cls, node: Node, before: List[Any] | None = None):
        if node.text is None:
            raise ValueError("Identifier has no name")

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        condition_node = node.child_by_field_name("condition")
        if condition_node is None or condition_node.text is None:
            raise ValueError("Assertion has no condition")
        condition = tree_sitter_node_to_expression(condition_node)
        condition_expression = cls(expression=condition, before=before or [])

        body_node = node.child_by_field_name("body")

        body = tree_sitter_node_to_expression(body_node)
        body.before.append(condition_expression)
        body.before.append(empty_line)
        return body

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        indentation = "" if inline else " " * (indent - 2)
        return f"{indentation}assert {self.expression.rebuild()};"


__all__ = ["Assertion"]
