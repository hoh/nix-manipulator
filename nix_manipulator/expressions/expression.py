from __future__ import annotations

from typing import List, Any

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node


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


