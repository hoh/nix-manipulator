from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression, TypedExpression


class BinaryExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"binary_expression"}
    operator: str
    left: NixExpression
    right: NixExpression

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.type == "binary_expression":
            left_node, operator_node, right_node = node.children
            operator = operator_node.text.decode()
            left = tree_sitter_node_to_expression(left_node)
            right = tree_sitter_node_to_expression(right_node)
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")

        return cls(operator=operator, left=left, right=right)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        left_str = self.left.rebuild(indent=indent, inline=True)
        right_str = self.right.rebuild(indent=indent, inline=True)

        indentation = "" if inline else " " * indent

        if self.operator == "++" and not inline:
            return self.add_trivia(
                f"{left_str}\n{indentation}{self.operator} {right_str}", indent, inline
            )
        else:
            return self.add_trivia(
                f"{left_str} {self.operator} {right_str}", indent, inline
            )


__all__ = ["BinaryExpression"]
