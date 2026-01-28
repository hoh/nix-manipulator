from __future__ import annotations

from dataclasses import dataclass

from nix_manipulator.expressions.expression import NixExpression


@dataclass(slots=True, repr=False)
class RawExpression(NixExpression):
    """Fallback expression that preserves raw source text."""

    text: str

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Return raw source to avoid losing unsupported formatting."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        if not self.before and not self.after:
            return self.text
        return self.add_trivia(self.text, indent=0, inline=True)


__all__ = ["RawExpression"]
