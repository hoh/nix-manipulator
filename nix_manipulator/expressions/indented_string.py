from __future__ import annotations

from typing import ClassVar, Union

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


class IndentedString(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "indented_string_expression",
    }
    value: Union[str, int, bool]

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing expression")
        value = node.text.decode().strip("''")
        return cls(value=value)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        value_str = f"''{self.value}''"

        return self.add_trivia(value_str, indent, inline)

    def __repr__(self):
        return f"IndentedString(\nvalue={self.value}\n)"


__all__ = ["IndentedString"]
