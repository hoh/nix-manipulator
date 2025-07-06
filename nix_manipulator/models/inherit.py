from __future__ import annotations

from typing import List, Any

from tree_sitter import Node

from nix_manipulator.format import _format_trivia
from nix_manipulator.models.expression import NixExpression
from nix_manipulator.models.identifier import NixIdentifier
from nix_manipulator.models.layout import linebreak


class NixInherit(NixExpression):
    names: List[NixIdentifier]

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        names: list[NixIdentifier]
        for child in node.children:
            if child.type == "inherited_attrs":
                names = [
                    NixIdentifier.from_cst(grandchild) for grandchild in child.children
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
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)

        if self.after and self.after[-1] != linebreak and after_str[-1] == "\n":
            after_str = after_str[:-1]

        indentation = " " * indent if not inline else ""
        names = " ".join(name.rebuild(inline=True) for name in self.names)
        return f"{before_str}{indentation}inherit {names};" + (
            f"\n{after_str}" if after_str else ""
        )
