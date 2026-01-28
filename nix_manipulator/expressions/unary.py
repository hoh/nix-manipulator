from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression,
                                                    coerce_expression)
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.trivia import (
    collect_comment_trivia_between, format_interstitial_trivia_with_separator,
    gap_between, layout_from_gap)


@dataclass(slots=True, repr=False)
class UnaryExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"unary_expression"}
    operator: str
    expression: NixExpression
    operand_gap: str = ""
    between: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize operands so unary operations behave consistently."""
        NixExpression.__post_init__(self)
        if isinstance(self.expression, (int, float)) or self.expression is None:
            self.expression = coerce_expression(self.expression)

    @classmethod
    def from_cst(cls, node: Node):
        """Preserve unary spacing/comments so negations round-trip faithfully."""
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.type != "unary_expression":
            raise ValueError(f"Unsupported expression type: {node.type}")

        content_nodes = [child for child in node.children if child.type != "comment"]
        if len(content_nodes) < 2:
            raise ValueError("Unary expression is incomplete")
        operator_node, expression_node = content_nodes[0], content_nodes[1]
        if operator_node.text is None:
            raise ValueError("Unary operator missing")
        operator = operator_node.text.decode()
        expression = tree_sitter_node_to_expression(expression_node)

        comment_nodes = [
            child
            for child in node.children
            if child.type == "comment"
            and operator_node.end_byte <= child.start_byte < expression_node.start_byte
        ]
        between: list[Any] = []
        operand_gap = gap_between(node, operator_node, expression_node)
        if comment_nodes:
            between = collect_comment_trivia_between(
                node,
                comment_nodes,
                operator_node,
                expression_node,
                allow_inline=True,
            )
            comment_nodes.sort(key=lambda child: child.start_byte)
            operand_gap = gap_between(node, comment_nodes[-1], expression_node)

        return cls(
            operator=operator,
            expression=expression,
            operand_gap=operand_gap,
            between=between,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct unary expression while retaining operator spacing."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        operand_layout = layout_from_gap(self.operand_gap)
        if self.between:
            operand_layout = operand_layout.model_copy(update={"blank_line": False})

        force_newline = any(
            item in (linebreak, empty_line) or isinstance(item, Comment)
            for item in self.between
        )
        if force_newline and not operand_layout.on_newline:
            operand_layout = operand_layout.model_copy(
                update={
                    "on_newline": True,
                    "blank_line": any(item is empty_line for item in self.between),
                }
            )

        if operand_layout.on_newline:
            operand_indent = (
                operand_layout.indent
                if operand_layout.indent is not None
                else indent
            )
            expression_str = self.expression.rebuild(
                indent=operand_indent, inline=False
            )
        else:
            operand_indent = indent
            expression_str = self.expression.rebuild(indent=indent, inline=True)

        inline_sep = " " if self.between else ""
        between_str, operand_prefix = format_interstitial_trivia_with_separator(
            self.between,
            operand_layout,
            indent=indent,
            inline_sep=inline_sep,
            include_indent=False,
            drop_blank_line_if_items=False,
        )

        indentation = "" if inline else " " * indent
        if self.operator == "++" and not inline:
            base = f"\n{indentation}{self.operator}"
        else:
            base = f"{self.operator}"

        return self.add_trivia(
            f"{base}{between_str}{operand_prefix}{expression_str}", indent, inline
        )


__all__ = ["UnaryExpression"]
