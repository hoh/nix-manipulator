from __future__ import annotations

from tree_sitter import Node

from nix_manipulator.format import _format_trivia
from nix_manipulator.expressions.expression import NixExpression


class NixBinaryExpression(NixExpression):
    operator: str
    left: NixExpression
    right: NixExpression

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.cst.models import NODE_TYPE_TO_CLASS

        if node.type == "binary_expression":
            left_node, operator_node, right_node = node.children
            operator = operator_node.text.decode()
            left = NODE_TYPE_TO_CLASS.get(left_node.type).from_cst(left_node)
            right = NODE_TYPE_TO_CLASS.get(right_node.type).from_cst(right_node)
        return cls(operator=operator, left=left, right=right)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent

        left_str = self.left.rebuild(indent=indent, inline=True)
        right_str = self.right.rebuild(indent=indent, inline=True)

        return f"{before_str}{indentation}{left_str} {self.operator} {right_str}{after_str}"
