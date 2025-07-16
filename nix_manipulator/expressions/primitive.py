from __future__ import annotations

import json
from typing import ClassVar, Union

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression
from nix_manipulator.expressions.identifier import Identifier


class Primitive(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "integer_expression",
        "string_expression",
        "variable_expression",
    }
    value: Union[str, int, bool]

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing expression")

        if node.type == "string_expression":
            value = json.loads(node.text)
        elif node.type == "string_fragment":
            value = node.text.decode()
        elif node.type == "integer_expression":
            value = int(node.text)
        elif node.type == "variable_expression":
            if node.text in (b"true", b"false"):
                value = node.text == b"true"
            else:
                return Identifier(name=node.text.decode())
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")
        return cls(value=value)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        if isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        elif isinstance(self.value, int):
            value_str = f"{self.value}"
        else:
            raise ValueError(f"Unsupported expression type: {type(self.value)}")

        return self.add_trivia(value_str, indent, inline)

    def __repr__(self):
        return f"NixExpression(\nvalue={self.value} type={type(self.value)}\n)"


__all__ = ["Primitive"]
