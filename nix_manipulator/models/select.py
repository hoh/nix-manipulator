from __future__ import annotations

from tree_sitter import Node

from nix_manipulator.format import _format_trivia
from nix_manipulator.models.expression import NixExpression
from nix_manipulator.models.identifier import NixIdentifier


class NixSelect(NixExpression):
    expression: NixIdentifier
    attribute: NixIdentifier

    @classmethod
    def from_cst(cls, node: Node) -> NixSelect:
        return cls(
            expression=NixIdentifier(
                name=node.child_by_field_name("expression").text.decode()
            ),
            attribute=NixIdentifier(
                name=node.child_by_field_name("attrpath").text.decode()
            ),
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct select expression."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent
        return f"{before_str}{indentation}{self.expression.name}.{self.attribute.name}{after_str}"
