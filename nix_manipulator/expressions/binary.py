from __future__ import annotations

import re
from typing import ClassVar

from pydantic import field_validator
from tree_sitter import Node

from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.operator import Operator
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.expression import NixExpression, TypedExpression


class BinaryExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"binary_expression"}
    operator: Operator
    left: NixExpression
    right: NixExpression

    @field_validator("left", "right", mode="before")
    @classmethod
    def validate_left_right(cls, value) -> NixExpression:
        """Convert primitive values to Primitive expressions."""
        if isinstance(value, int):
            return Primitive(value=value)
        else:
            return value

    @field_validator("operator", mode="before")
    @classmethod
    def validate_operator(cls, value: Operator | str) -> Operator:
        """Convert operators expressed as string to Operator instances."""
        if isinstance(value, Operator):
            return value
        elif isinstance(value, str):
            return Operator(name=value)
        else:
            raise ValueError(f"Unsupported operator type: {type(value)}")


    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.type == "binary_expression":

            # Associate comments to the components (left, operator or right) of the binary expression.
            children = []
            comments = []
            previous_child = None
            for child in node.children:
                if child.type == "comment":
                    if previous_child:
                        gap = node.parent.parent.parent.text[
                            previous_child.end_byte: child.start_byte
                        ].decode()
                        if re.match(r"\s*\n", gap):
                            comments.append(empty_line)
                    comments.append(Comment.from_cst(node=child))
                else:
                    children.append(child)
                previous_child = child

            left_node, operator_node, right_node = children
            operator = Operator(name=operator_node.text.decode(), before=comments)
            left = tree_sitter_node_to_expression(left_node)
            right = tree_sitter_node_to_expression(right_node)
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")

        return cls(operator=operator, left=left, right=right)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        left_str = self.left.rebuild(indent=indent, inline=True)
        right_str = self.right.rebuild(indent=indent, inline=True)

        indentation = "" if inline else " " * indent

        if self.operator.name == "++" and not inline:
            return self.add_trivia(
                f"{left_str}\n{indentation}{self.operator.rebuild()} {right_str}", indent, inline
            )
        else:
            operator_str = self.operator.rebuild(indent=indent)
            if not operator_str.startswith("\n"):
                # Ensure exactly one space before the operator (avoid double spaces)
                operator_str = " " + operator_str.lstrip()
            return self.add_trivia(
                f"{left_str}{operator_str} {right_str}", indent, inline
            )


__all__ = ["BinaryExpression"]
