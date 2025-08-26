from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions import TypedExpression


class Ellipses(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"ellipses"}

    @classmethod
    def from_cst(cls, node: Node):
        return cls()

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        comma = "," if trailing_comma else ""
        return self.add_trivia(f"...{comma}", indent, inline)

    def __repr__(self):
        return f"Ellipses"
