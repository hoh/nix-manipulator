from dataclasses import dataclass
from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


@dataclass(slots=True, repr=False)
class Ellipses(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"ellipses"}

    @classmethod
    def from_cst(cls, node: Node):
        """Treat ellipses as a structural placeholder for function formals."""
        return cls()

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        comma = "," if trailing_comma else ""
        return self.add_trivia(f"...{comma}", indent, inline)
