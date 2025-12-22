from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression,
                                                    coerce_expression)
from nix_manipulator.expressions.operator import Operator
from nix_manipulator.expressions.trivia import (
    collect_comment_trivia_between, collect_trailing_comment_trivia,
    gap_line_info, split_inline_comments)

_CHAINABLE_OPERATORS = {"++", "//", "+", "&&", "||", "->"}


@dataclass(slots=True)
class _OperandSlot:
    expr: NixExpression
    extra_before: list[Any]
    extra_after: list[Any]


def _clone_with_trivia(
    expr: NixExpression,
    extra_before: list[Any] | None,
    extra_after: list[Any] | None,
) -> NixExpression:
    """Stage trivia merges without mutating original operands."""
    if not extra_before and not extra_after:
        return expr
    updated = expr.model_copy()
    if extra_before:
        updated.before = list(extra_before) + list(updated.before)
    if extra_after:
        updated.after = list(updated.after) + list(extra_after)
    return updated


def _rebuild_operand(
    expr: NixExpression,
    *,
    indent: int,
    inline: bool,
    extra_before: list[Any] | None = None,
    extra_after: list[Any] | None = None,
) -> str:
    """Rebuild operands with merged trivia so chaining preserves comments."""
    expr = _clone_with_trivia(expr, extra_before, extra_after)
    if inline and getattr(expr, "before", None):
        return expr.rebuild(indent=indent, inline=False)
    return expr.rebuild(indent=indent, inline=inline)


def _ensure_indent(text: str, indent: int) -> str:
    """Guard against under-indented multiline fragments during rebuild."""
    if not text:
        return text
    first_line = text.split("\n", 1)[0]
    if first_line == "":
        return text
    leading = len(first_line) - len(first_line.lstrip(" "))
    if leading < indent:
        text = (" " * (indent - leading)) + text
    return text


def _is_absorbable_term(expr: NixExpression) -> bool:
    """Return True for RFC absorbable terms (lists, sets, indented strings)."""
    from nix_manipulator.expressions.indented_string import IndentedString
    from nix_manipulator.expressions.list import NixList
    from nix_manipulator.expressions.parenthesis import Parenthesis
    from nix_manipulator.expressions.set import AttributeSet

    if isinstance(expr, Parenthesis):
        return _is_absorbable_term(expr.value)
    if isinstance(expr, NixList):
        if expr.multiline is None and len(expr.value) > 1:
            return False
        return True
    return isinstance(expr, (AttributeSet, IndentedString))


def _has_leading_comment(expr: NixExpression) -> bool:
    """True when leading trivia includes a non-inline comment."""
    for item in expr.before:
        if isinstance(item, Comment) and not item.inline:
            return True
    return False


def _should_absorb_chainable_operand(expr: NixExpression) -> bool:
    """Absorb only when the term is absorbable and has no leading comments."""
    return _is_absorbable_term(expr) and not _has_leading_comment(expr)


def _is_chainable_operator(name: str) -> bool:
    """Return True for operators that follow RFC chainable rules."""
    return name in _CHAINABLE_OPERATORS


def _collect_binary_comment_trivia(
    node: Node,
    left_node: Node,
    operator_node: Node,
    right_node: Node,
    left: NixExpression,
    right: NixExpression,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Route comment trivia to operands or operator based on location."""
    comment_nodes = [child for child in node.children if child.type == "comment"]

    comments_before_operator = collect_comment_trivia_between(
        node,
        comment_nodes,
        left_node,
        operator_node,
        allow_inline=True,
        include_linebreak=False,
        inline_requires_gap=True,
    )
    comments_before_operator, left_inline = split_inline_comments(
        comments_before_operator
    )
    if left_inline:
        left.after.extend(left_inline)

    comments_before_right = collect_comment_trivia_between(
        node,
        comment_nodes,
        operator_node,
        right_node,
        allow_inline=True,
        include_linebreak=False,
        inline_requires_gap=True,
    )
    comments_before_right, operator_after = split_inline_comments(
        comments_before_right
    )
    edge_comments = [
        comment
        for comment in comment_nodes
        if comment.start_byte == right_node.end_byte
    ]
    if edge_comments:
        edge_comments.sort(key=lambda comment: comment.start_byte)
        comments_before_right.extend(
            Comment.from_cst(comment_node) for comment_node in edge_comments
        )

    right_after = collect_trailing_comment_trivia(
        node,
        comment_nodes,
        right_node,
        allow_inline=True,
        include_linebreak=False,
        inline_requires_gap=True,
    )

    return comments_before_operator, comments_before_right, operator_after, right_after


def _format_chained_binary(
    expr: "BinaryExpression", *, indent: int, inline: bool
) -> str | None:
    """Special-case chained ops to keep formatting stable across merges."""
    if expr.operator.name not in ("//", "++") or not expr.operator_gap_lines:
        return None

    operands: list[_OperandSlot] = []
    operators: list[tuple[Operator, int, int]] = []

    def collect(cur: NixExpression, *, include_trivia: bool = True) -> tuple[int, int]:
        """Flatten chained operators so rebuild can honor original spacing."""
        if (
            isinstance(cur, BinaryExpression)
            and cur.operator.name == expr.operator.name
        ):
            left_start, left_end = collect(cur.left)
            operators.append(
                (
                    cur.operator,
                    cur.operator_gap_lines,
                    cur.right_gap_lines,
                )
            )
            right_start, right_end = collect(cur.right)
            if include_trivia:
                if cur.before:
                    operands[left_start].extra_before = list(
                        cur.before
                    ) + operands[left_start].extra_before
                if cur.after:
                    operands[right_end].extra_after.extend(cur.after)
            return left_start, right_end
        operands.append(_OperandSlot(expr=cur, extra_before=[], extra_after=[]))
        idx = len(operands) - 1
        return idx, idx

    collect(expr, include_trivia=False)

    if len(operands) <= 1:
        return None

    first = operands[0]
    rebuilt = _rebuild_operand(
        first.expr,
        indent=indent,
        inline=True,
        extra_before=first.extra_before,
        extra_after=first.extra_after,
    )
    for (
        operator,
        op_gap_lines,
        right_gap_lines,
    ), operand_slot in zip(operators, operands[1:]):
        op_newline = op_gap_lines > 0
        right_newline = right_gap_lines > 0
        operator_str = operator.rebuild(indent=indent)
        if op_newline:
            op_sep = "\n" * op_gap_lines if op_gap_lines else "\n"
            if right_newline:
                right_sep = "\n" * right_gap_lines if right_gap_lines else "\n"
                right_indent = (
                    indent
                    if _should_absorb_chainable_operand(operand_slot.expr)
                    else indent + 2
                )
                right_str = _rebuild_operand(
                    operand_slot.expr,
                    indent=right_indent,
                    inline=True,
                    extra_before=operand_slot.extra_before,
                    extra_after=operand_slot.extra_after,
                )
                right_str = _ensure_indent(right_str, right_indent)
                rebuilt += f"{op_sep}{operator_str}{right_sep}{right_str}"
            else:
                right_str = _rebuild_operand(
                    operand_slot.expr,
                    indent=indent,
                    inline=True,
                    extra_before=operand_slot.extra_before,
                    extra_after=operand_slot.extra_after,
                )
                if not operator_str.endswith(" "):
                    operator_str = operator_str.rstrip() + " "
                rebuilt += f"{op_sep}{operator_str}{right_str}"
        else:
            right_str = _rebuild_operand(
                operand_slot.expr,
                indent=indent,
                inline=True,
                extra_before=operand_slot.extra_before,
                extra_after=operand_slot.extra_after,
            )
            if not operator_str.startswith("\n"):
                operator_str = " " + operator_str.lstrip()
            rebuilt += f"{operator_str} {right_str}"

    return expr.add_trivia(rebuilt, indent, inline)


def _resolve_right_operand(
    expr: "BinaryExpression", *, indent: int
) -> tuple[str, int]:
    """Resolve right operand indentation for multiline operators."""
    if _is_chainable_operator(expr.operator.name):
        if (
            isinstance(expr.right, BinaryExpression)
            and expr.right.operator.name == expr.operator.name
            and expr.right.operator_gap_lines
        ):
            right_indent = indent
        elif _should_absorb_chainable_operand(expr.right):
            right_indent = indent
        else:
            right_indent = indent + 2
    else:
        right_indent = indent
    right_str = _rebuild_operand(expr.right, indent=right_indent, inline=True)
    right_str = _ensure_indent(right_str, right_indent)
    return right_str, right_indent


@dataclass(slots=True)
class BinaryExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"binary_expression"}
    operator: Operator
    left: NixExpression
    right: NixExpression
    operator_gap_lines: int = 0
    right_gap_lines: int = 0

    def __post_init__(self) -> None:
        """Convert primitive values to their expression equivalents."""
        NixExpression.__post_init__(self)
        if isinstance(self.left, (int, float)) or self.left is None:
            self.left = coerce_expression(self.left)
        if isinstance(self.right, (int, float)) or self.right is None:
            self.right = coerce_expression(self.right)
        if isinstance(self.operator, str):
            self.operator = Operator(name=self.operator)
        elif not isinstance(self.operator, Operator):
            raise ValueError(f"Unsupported operator type: {type(self.operator)}")

    @classmethod
    def from_cst(cls, node: Node):
        """Capture operator spacing to preserve line breaks in chained binaries."""
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        if node.type == "binary_expression":

            # Associate comments to the components (left, operator or right) of the binary expression.
            children = [child for child in node.children if child.type != "comment"]
            left_node, operator_node, right_node = children
            left = tree_sitter_node_to_expression(left_node)
            right = tree_sitter_node_to_expression(right_node)

            (
                comments_before_operator,
                comments_before_right,
                operator_after,
                right_after,
            ) = _collect_binary_comment_trivia(
                node,
                left_node,
                operator_node,
                right_node,
                left,
                right,
            )
            operator_gap_lines, _ = gap_line_info(node, left_node, operator_node)
            right_gap_lines, _ = gap_line_info(
                node,
                operator_node,
                right_node,
            )
            if comments_before_operator and operator_gap_lines:
                operator_gap_lines = 1
            if comments_before_right and right_gap_lines:
                right_gap_lines = 1
            if operator_node.text is None:
                raise ValueError("Missing operator")
            operator = Operator(
                name=operator_node.text.decode(),
                before=comments_before_operator,
                after=operator_after,
            )
            if comments_before_right:
                right.before = comments_before_right + right.before
            if right_after:
                right.after.extend(right_after)
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")

        return cls(
            operator=operator,
            left=left,
            right=right,
            operator_gap_lines=operator_gap_lines,
            right_gap_lines=right_gap_lines,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        chained = _format_chained_binary(self, indent=indent, inline=inline)
        if chained is not None:
            return chained

        left_str = self.left.rebuild(indent=indent, inline=True)
        right_str = self.right.rebuild(indent=indent, inline=True)

        operator_newline = self.operator_gap_lines > 0
        operator_str = self.operator.rebuild(indent=indent)

        if operator_newline:
            op_sep = (
                "\n" * self.operator_gap_lines if self.operator_gap_lines else "\n"
            )
            if self.right_gap_lines:
                right_sep = (
                    "\n" * self.right_gap_lines if self.right_gap_lines else "\n"
                )
                right_str, _ = _resolve_right_operand(self, indent=indent)
                return self.add_trivia(
                    f"{left_str}{op_sep}{operator_str}{right_sep}{right_str}",
                    indent,
                    inline,
                )
            return self.add_trivia(
                f"{left_str}{op_sep}{operator_str} {right_str}", indent, inline
            )

        if self.right_gap_lines:
            if not operator_str.startswith("\n"):
                operator_str = " " + operator_str.lstrip()
            right_sep = (
                "\n" * self.right_gap_lines if self.right_gap_lines else "\n"
            )
            right_str, _ = _resolve_right_operand(self, indent=indent)
            return self.add_trivia(
                f"{left_str}{operator_str}{right_sep}{right_str}", indent, inline
            )

        if not operator_str.startswith("\n"):
            # Ensure exactly one space before the operator (avoid double spaces)
            operator_str = " " + operator_str.lstrip()
        return self.add_trivia(
            f"{left_str}{operator_str} {right_str}", indent, inline
        )


__all__ = ["BinaryExpression"]
