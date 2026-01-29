from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


def _escape_indented_string(value: str) -> str:
    """Escape indented strings so the closing delimiter stays unambiguous."""
    escaped = value.replace("''", "'''")
    if escaped.endswith("'"):
        raise ValueError("Indented string cannot end with a single quote")
    return escaped


@dataclass(slots=True, repr=False)
class IndentedString(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "indented_string_expression",
    }
    value: str
    raw_string: bool = False

    @classmethod
    def from_cst(cls, node: Node):
        """Retain indented string payloads to preserve literal formatting."""
        if node.text is None:
            raise ValueError("Missing expression")
        text = node.text.decode()
        if text.startswith("''") and text.endswith("''"):
            value = text[2:-2]
        else:
            value = text
        return cls(value=value, raw_string=True)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        raw_value = (
            self.value if self.raw_string else _escape_indented_string(self.value)
        )
        value_str = f"''{raw_value}''"

        return self.add_trivia(value_str, indent, inline)


__all__ = ["IndentedString"]
