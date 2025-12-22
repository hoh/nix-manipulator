from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


@dataclass(slots=True)
class NixPath(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "path_expression",
        "spath_expression",
        "hpath_expression",
    }
    path: str

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ):
        """Capture raw path text to keep Nix path semantics intact."""
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
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        return self.add_trivia(self.path, indent, inline)


__all__ = ["NixPath"]
