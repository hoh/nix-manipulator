"""Top-level source code container preserving formatting trivia."""

from __future__ import annotations

from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.raw import RawExpression
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.trivia import (append_gap_trivia,
                                                append_gap_trivia_from_offsets,
                                                format_trivia,
                                                gap_from_offsets,
                                                parse_delimited_sequence,
                                                source_bytes_context,
                                                trim_trailing_layout_newline)
from nix_manipulator.expressions.with_statement import WithStatement
from nix_manipulator.mapping import tree_sitter_node_to_expression
from nix_manipulator.resolution import (attach_resolution_context,
                                        scopes_for_owner,
                                        set_resolution_context)


class NixSourceCode:
    """Represent a whole Nix file as a sequence of expressions and trivia."""
    tree_sitter_types: ClassVar[set[str]] = {"source_code"}
    node: Node
    expressions: list[Any]
    trailing: list[Any]
    contains_error: bool  # internal diagnostic; not part of the stable API

    def __init__(
        self,
        node: Node,
        expressions: list[Any],
        trailing: list[Any] | None = None,
        *,
        contains_error: bool = False,
    ):
        """Track CST root and trivia so rebuild can preserve formatting."""
        self.node = node
        self.expressions = expressions
        self.trailing = trailing or []
        self.contains_error = contains_error

    @classmethod
    def from_cst(cls, node: Node) -> NixSourceCode:
        """Build a source wrapper that keeps trivia for round-trip fidelity."""
        if node.text is None:
            raise ValueError("Missing source text")
        source_bytes = node.text

        contains_error = False
        has_error_attr = getattr(node, "has_error", None)
        if has_error_attr is not None:
            contains_error = node.has_error
        else:
            def has_error(cur: Node) -> bool:
                """Scan CST nodes to decide when to preserve raw text."""
                if cur.type == "ERROR":
                    return True
                return any(has_error(child) for child in cur.children)

            contains_error = has_error(node)

        if contains_error:
            # Preserve the raw text so round-tripping doesn't lose information.
            raw_text = source_bytes.decode()
            return cls(
                node=node,
                expressions=[RawExpression(text=raw_text)],
                trailing=[],
                contains_error=True,
            )

        with source_bytes_context(source_bytes):
            children = node.children
            leading_trivia: list[Any] = []
            if children:
                leading_gap = gap_from_offsets(
                    node, node.start_byte, children[0].start_byte
                )
                append_gap_trivia(leading_trivia, leading_gap)

            def parse_item(child: Node, before_trivia: list[Any]):
                """Attach leading trivia to top-level expressions."""
                expression = tree_sitter_node_to_expression(child)
                if before_trivia:
                    expression.before = before_trivia + expression.before
                return expression

            def can_inline_comment(
                prev: Node | None, comment_node: Node, items: list
            ) -> bool:
                """Inline comments stay on the previous expression line."""
                return (
                    prev is not None
                    and comment_node.start_point.row == prev.end_point.row
                    and bool(items)
                )

            def attach_inline_comment(item: Any, comment: Any) -> None:
                """Keep inline comments with the preceding expression."""
                comment.inline = True
                item.after.append(comment)

            expressions, trailing = parse_delimited_sequence(
                node,
                children,
                parse_item=parse_item,
                can_inline_comment=can_inline_comment,
                attach_inline_comment=attach_inline_comment,
                initial_trivia=leading_trivia,
            )
            if children:
                append_gap_trivia_from_offsets(
                    trailing, node, children[-1].end_byte, node.end_byte
                )
            else:
                append_gap_trivia_from_offsets(
                    trailing, node, node.start_byte, node.end_byte
                )

        return cls(
            node=node,
            expressions=expressions,
            trailing=trailing,
            contains_error=contains_error,
        )

    def rebuild(self) -> str:
        """Reassemble source with trailing trivia to keep file structure."""
        rebuilt = "".join(obj.rebuild() for obj in self.expressions)
        if not self.trailing:
            return rebuilt

        trailing_str = format_trivia(self.trailing, indent=0)
        trailing_str = trim_trailing_layout_newline(self.trailing, trailing_str)
        if trailing_str:
            prefix = "\n" if rebuilt else ""
            return rebuilt + prefix + trailing_str
        if self.trailing and self.trailing[-1] in (linebreak, empty_line):
            return rebuilt + ("\n" if not rebuilt.endswith("\n") else "")
        return rebuilt

    def _resolve_target_set(self, *, _visited: set[int] | None = None):
        """Locate the top-level attribute set for operator-style access (internal helper)."""
        visited = _visited or set()
        if not self.expressions:
            raise ValueError("Source contains no expressions")
        if len(self.expressions) != 1:
            raise ValueError("Source must contain exactly one top-level expression")

        expr = self.expressions[0]

        def resolve_from_expr(target, scopes=None):
            if id(target) in visited:
                raise ValueError("Top-level expression must be an attribute set")
            visited.add(id(target))

            if scopes is None:
                scopes = scopes_for_owner(target)

            def resolve_nested(expr, *, scopes=scopes):
                return resolve_from_expr(expr, scopes=scopes)

            match target:
                case Assertion():
                    if target.body is None:
                        raise ValueError("Unexpected assertion without body")
                    return resolve_nested(target.body, scopes=scopes)
                case LetExpression():
                    return resolve_nested(target.value, scopes=scopes)
                case FunctionDefinition():
                    output = target.output
                    if isinstance(output, FunctionCall):
                        argument = output.argument
                        while isinstance(argument, Parenthesis):
                            argument = argument.value
                        if isinstance(argument, Identifier) and scopes:
                            set_resolution_context(argument, scopes)
                            argument = argument.value
                        if isinstance(argument, AttributeSet):
                            return argument
                    if output is None:
                        raise ValueError("Top-level expression must be an attribute set")
                    try:
                        return resolve_nested(output, scopes=scopes)
                    except ValueError as exc:
                        raise ValueError("Top-level expression must be an attribute set") from exc
                case WithStatement():
                    body_scopes = scopes_for_owner(target) or scopes
                    attach_resolution_context(target.body, owner=target)
                    return resolve_from_expr(target.body, scopes=body_scopes)
                case Identifier():
                    identifier_scopes = scopes or scopes_for_owner(target)
                    if identifier_scopes:
                        set_resolution_context(target, identifier_scopes)
                    resolved = target.value
                    return resolve_nested(resolved, scopes=identifier_scopes)
                case Parenthesis():
                    return resolve_nested(target.value, scopes=scopes)
                case AttributeSet():
                    return target
                case FunctionCall():
                    argument = target.argument
                    while isinstance(argument, Parenthesis):
                        argument = argument.value
                    if isinstance(argument, Identifier) and scopes:
                        set_resolution_context(argument, scopes)
                        argument = argument.value
                    if isinstance(argument, AttributeSet):
                        return argument
            raise ValueError("Top-level expression must be an attribute set")

        return resolve_from_expr(expr)

    def __getitem__(self, key: str):
        """Expose dict-style access to the top-level attribute set."""
        target_set = self._resolve_target_set()
        return target_set[key]

    def __setitem__(self, key: str, value):
        """Update the top-level attribute set for operator-style edits."""
        if not self.expressions:
            self.expressions = [
                AttributeSet(values=[Binding(name=key, value=value)], multiline=False)
            ]
            return

        target_set = self._resolve_target_set()
        target_set[key] = value

    def __delitem__(self, key: str):
        """Remove a binding and normalize empty results for operator usage."""
        target_set = self._resolve_target_set()
        del target_set[key]

    def __eq__(self, other: object) -> bool:
        """Allow comparisons against expressions or raw text for tests."""
        if isinstance(other, NixSourceCode):
            if self.contains_error or other.contains_error:
                return (
                    self.contains_error
                    and other.contains_error
                    and self.rebuild() == other.rebuild()
                )
            return (
                self.expressions == other.expressions
                and self.trailing == other.trailing
            )

        if isinstance(other, NixExpression):
            if self.contains_error:
                return False
            if (
                len(self.expressions) == 1
                and not self.trailing
                and self.expressions[0] == other
            ):
                return True
            return self.rebuild() == other.rebuild()
        if isinstance(other, str):
            if self.contains_error:
                return False
            return self.rebuild() == other
        return False

    def __repr__(self) -> str:
        """Render rebuilt Nix code for REPL/debug output."""
        try:
            return self.rebuild()
        except Exception as exc:  # pragma: no cover - repr fallback path
            return f"<NixSourceCode unprintable: {exc!r}>"

    @property
    def expr(self) -> Any:
        """Return the first top-level expression."""
        return self.expressions[0]


__all__ = ["NixSourceCode"]
