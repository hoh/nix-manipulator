from __future__ import annotations

from typing import Any, ClassVar, List

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression
from nix_manipulator.expressions.identifier import Identifier


class Inherit(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"inherit"}
    names: List[Identifier]

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        names: list[Identifier]
        for child in node.children:
            if child.type == "inherited_attrs":
                names = [
                    Identifier.from_cst(grandchild) for grandchild in child.children
                ]
                break
        else:
            names = []

        return cls(names=names, before=before or [], after=after or [])

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        names = " ".join(name.rebuild(inline=True) for name in self.names)
        return self.add_trivia(f"inherit {names};", indent, inline)


__all__ = ["Inherit"]
