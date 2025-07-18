from __future__ import annotations

from typing import Any, List, Optional

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression


class Identifier(NixExpression):
    name: str
    default_value: Optional[NixExpression] = None

    @classmethod
    def from_cst(cls, node: Node, before: List[Any] | None = None):
        if node.text is None:
            raise ValueError("Identifier has no name")
        name = node.text.decode()
        return cls(name=name, before=before or [])

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        comma = "," if trailing_comma else ""
        if self.default_value is not None:
            return self.add_trivia(
                f"{self.name} ? {self.default_value.rebuild(inline=True)}{comma}",
                indent,
                inline,
            )
        else:
            return self.add_trivia(f"{self.name}{comma}", indent, inline)


__all__ = ["Identifier"]
