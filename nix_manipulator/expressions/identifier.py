from __future__ import annotations

from typing import Any, List

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.layout import linebreak
from nix_manipulator.format import _format_trivia


class NixIdentifier(NixExpression):
    name: str

    @classmethod
    def from_cst(cls, node: Node, before: List[Any] | None = None):
        name = node.text.decode()
        return cls(name=name, before=before or [])

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        comma = "," if trailing_comma else ""

        if self.after and self.after[-1] != linebreak and after_str[-1] == "\n":
            after_str = after_str[:-1]

        indentation = " " * indent if not inline else ""
        return f"{before_str}{indentation}{self.name}{comma}" + (
            f"\n{after_str}" if after_str else ""
        )
