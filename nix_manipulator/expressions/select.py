from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression
from nix_manipulator.expressions.identifier import Identifier


class Select(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"select_expression"}
    expression: Identifier
    attribute: Identifier

    @classmethod
    def from_cst(cls, node: Node) -> Select:
        if node.text is None:
            raise ValueError("Select expression is missing")
        return cls(
            expression=Identifier(
                name=node.child_by_field_name("expression").text.decode()
            ),
            attribute=Identifier(
                name=node.child_by_field_name("attrpath").text.decode()
            ),
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct select expression."""
        return self.add_trivia(
            f"{self.expression.name}.{self.attribute.name}", indent, inline
        )


__all__ = ["Select"]
