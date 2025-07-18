from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.format import _format_trivia


class WithStatement(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"with_expression"}
    environment: NixExpression
    body: NixExpression
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing text in with statement")

        environment_node = node.child_by_field_name("environment")
        body_node = node.child_by_field_name("body")
        multiline = b"\n" in node.text

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        environment = tree_sitter_node_to_expression(environment_node)
        body = tree_sitter_node_to_expression(body_node)
        return cls(environment=environment, body=body, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct with expression."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)

        environment_str = self.environment.rebuild(indent=indent, inline=True)
        body_str = self.body.rebuild(indent=indent, inline=True)

        return f"{before_str}with {environment_str}; {body_str}{after_str}"


__all__ = ["WithStatement"]
