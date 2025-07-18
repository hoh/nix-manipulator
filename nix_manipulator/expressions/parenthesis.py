from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions import NixExpression, TypedExpression


class Parenthesis(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"parenthesized_expression"}
    value: NixExpression

    @classmethod
    def from_cst(cls, node: Node) -> Parenthesis:
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        assert len(node.children) == 3
        assert node.children[0].type == "("
        assert node.children[2].type == ")"

        value = tree_sitter_node_to_expression(node.children[1])
        return cls(value=value)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        value_str = f"({self.value.rebuild(indent=indent, inline=True)})"
        return self.add_trivia(value_str, indent, inline)

    def __repr__(self):
        return f"Parenthesis(\nvalue={self.value}\n)"


__all__ = ["Parenthesis"]
