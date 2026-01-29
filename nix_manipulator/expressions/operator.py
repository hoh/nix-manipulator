from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression


@dataclass(slots=True, repr=False)
class Operator(NixExpression):
    # name: Literal["++", "+", "-", "*", "/"]
    name: str

    @classmethod
    def from_cst(cls, node: Node) -> Operator:
        """Preserve operator tokens to keep spacing and semantics stable."""
        if node.text is None:
            raise ValueError("Missing operator")
        return cls(name=node.text.decode())

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        value_str = self.name
        return self.add_trivia(value_str, indent, inline)


__all__ = ["Operator"]
