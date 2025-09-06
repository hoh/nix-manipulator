from __future__ import annotations

from typing import ClassVar

from pydantic import field_validator
from tree_sitter import Node

from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.expression import NixExpression, TypedExpression


class UnaryExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"unary_expression"}
    operator: str
    expression: NixExpression

    @field_validator("expression", mode="before")
    @classmethod
    def validate_left_right(cls, value) -> NixExpression:
        if isinstance(value, int):
            return Primitive(value=value)
        else:
            return value

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.type == "unary_expression":
            operator_node, expression_node = node.children
            operator = operator_node.text.decode()
            expression = tree_sitter_node_to_expression(expression_node)
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")

        return cls(operator=operator, expression=expression)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        expression_str = self.expression.rebuild(indent=indent, inline=True)

        indentation = "" if inline else " " * indent

        if self.operator == "++" and not inline:
            return self.add_trivia(
                f"\n{indentation}{self.operator}{expression_str}", indent, inline
            )
        else:
            return self.add_trivia(
                f"{self.operator}{expression_str}", indent, inline
            )


__all__ = ["UnaryExpression"]
