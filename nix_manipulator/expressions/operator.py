from __future__ import annotations

from typing import Literal

from nix_manipulator.expressions.expression import NixExpression


class Operator(NixExpression):
    # name: Literal["++", "+", "-", "*", "/"]
    name: str

    @classmethod
    def from_cst(cls, name: str) -> Operator:
        return cls(name=name)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        value_str = self.name
        return self.add_trivia(value_str, indent, inline)

    def __repr__(self):
        return f"NixExpression(\nname={self.name}\n)"


__all__ = ["Operator"]
