from __future__ import annotations

from typing import List, Any

from tree_sitter import Node

from nix_manipulator.format import _format_trivia
from nix_manipulator.expressions.expression import NixExpression


class NixPath(NixExpression):
    path: str

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        path = node.text.decode()
        return cls(path=path, before=before or [], after=after or [])

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        indentation = " " * indent if not inline else ""
        return f"{before_str}{indentation}{self.path}{after_str}"
