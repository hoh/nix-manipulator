from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression, NixExpression


class IfExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"if_expression",}
    condition: NixExpression
    consequence: NixExpression
    alternative: NixExpression

    @classmethod
    def from_cst(cls, node: Node) -> IfExpression:
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        return cls(
            condition=tree_sitter_node_to_expression(node.child_by_field_name("condition")),
            consequence=tree_sitter_node_to_expression(node.child_by_field_name("consequence")),
            alternative=tree_sitter_node_to_expression(node.child_by_field_name("alternative")),
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if_str = self.condition.rebuild(indent=indent, inline=True)
        then_str = self.consequence.rebuild(indent=indent, inline=True)
        else_str = self.alternative.rebuild(indent=indent, inline=True)

        # Format as: if <condition> then <then_expr> else <else_expr>
        rebuild_string = f"if {if_str} then\n  {then_str}\nelse\n  {else_str}"

        return self.add_trivia(rebuild_string, indent, inline)

    def __repr__(self):
        return f"IfExpression(\nif={self.condition}\n)"


__all__ = ["IfExpression"]
