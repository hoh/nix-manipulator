from __future__ import annotations

from typing import Any, ClassVar, List

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


class NixPath(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"path_expression"}
    path: str

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        if node.text is None:
            raise ValueError("Path is missing")
        path = node.text.decode()
        return cls(path=path, before=before or [], after=after or [])

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        return self.add_trivia(self.path, indent, inline)


__all__ = ["NixPath"]
