from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


@dataclass(slots=True, repr=False)
class FloatExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"float_expression"}
    value: str

    @classmethod
    def from_cst(cls, node: Node):
        """Preserve float token text so round-trip formatting stays identical."""
        if node.text is None:
            raise ValueError("Missing expression")
        return cls(value=node.text.decode())

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        return self.add_trivia(self.value, indent, inline)


__all__ = ["FloatExpression"]
