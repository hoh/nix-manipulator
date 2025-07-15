from __future__ import annotations

from typing import Any, ClassVar, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node

from nix_manipulator.expressions.layout import linebreak


class NixExpression(BaseModel):
    """Base class for all Nix objects."""

    model_config = ConfigDict(extra="forbid")

    before: List[Any] = Field(default_factory=list)
    after: List[Any] = Field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node):
        """Construct an object from a CST node."""
        raise NotImplementedError

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct the Nix source code for this object."""
        raise NotImplementedError

    def add_trivia(
        self,
        rebuild_string: str,
        indent: int,
        inline: bool,
        after_str: Optional[str] = None,
    ) -> str:
        from nix_manipulator.format import _format_trivia

        before_str = _format_trivia(self.before, indent=indent)
        after_str = (
            after_str
            if after_str is not None
            else _format_trivia(self.after, indent=indent)
        )
        indentation = " " * indent if not inline else ""

        if self.after and self.after[-1] != linebreak and after_str[-1] == "\n":
            after_str = after_str[:-1]

        return f"{before_str}{indentation}{rebuild_string}" + (
            f"\n{after_str}" if after_str else ""
        )


class TypedExpression(NixExpression):
    """Base class for all Nix objects matching a tree-sitter type."""

    tree_sitter_types: ClassVar[set[str]]


__all__ = ["NixExpression", "TypedExpression"]
