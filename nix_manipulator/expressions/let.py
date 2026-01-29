"""Let/in expressions with trivia-aware parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.binding_parser import parse_binding_sequence
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.scope import ScopeLayer, ScopeState
from nix_manipulator.expressions.set import _collect_attrpath_order, _render_bindings
from nix_manipulator.expressions.trivia import (
    append_gap_between_offsets,
    collect_comment_trivia_between,
    format_trivia,
    gap_has_empty_line_from_offsets,
    gap_has_newline_from_offsets,
)


@dataclass(slots=True, repr=False)
class LetExpression(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"let_expression"}
    local_variables: list[Binding | Inherit]
    value: NixExpression
    after_let_comment: Comment | None = None
    attrpath_order: list[Any] = field(default_factory=list, compare=False)

    @classmethod
    def from_cst(cls, node: Node) -> LetExpression:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        if node.text is None:
            raise ValueError("Attribute set has no code")

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        after_let_comment: Comment | None = None
        outer_comments: list[Node] = []

        let_symbol: Node | None = None
        in_symbol: Node | None = None
        binding_set: Node | None = None
        for child in node.children:
            if child.type == "let":
                let_symbol = child
            elif child.type == "in":
                in_symbol = child
            elif child.type == "binding_set":
                binding_set = child
            elif child.type == "comment":
                outer_comments.append(child)
            else:
                pass

        if let_symbol is None or in_symbol is None:
            raise ValueError("Could not parse let expression")

        value_node = node.child_by_field_name("body")
        if value_node is None:
            value_node = next(
                (
                    child
                    for child in reversed(node.children)
                    if child.type not in ("comment", "let", "in")
                ),
                None,
            )
        if value_node is None:
            raise ValueError("Could not parse let body")
        value: NixExpression = tree_sitter_node_to_expression(value_node)

        def collect_outer_comments(
            start: Node, end: Node, *, allow_inline: bool = False
        ) -> list[Any]:
            """Retain outer comments so let structure matches original layout."""
            return collect_comment_trivia_between(
                node,
                outer_comments,
                start,
                end,
                allow_inline=allow_inline,
            )

        if binding_set is not None:
            for comment_node in list(outer_comments):
                if not (
                    let_symbol.end_byte
                    <= comment_node.start_byte
                    < binding_set.start_byte
                ):
                    continue
                if comment_node.start_point.row != let_symbol.end_point.row:
                    continue
                after_let_comment_expr = tree_sitter_node_to_expression(comment_node)
                assert isinstance(after_let_comment_expr, Comment)
                after_let_comment_expr.inline = True
                after_let_comment = after_let_comment_expr
                outer_comments.remove(comment_node)
                break

        pre_binding_comments: list[Any] = []
        post_binding_comments: list[Any] = []
        if binding_set is not None:
            pre_binding_comments = collect_outer_comments(let_symbol, binding_set)
            post_binding_comments = collect_outer_comments(
                binding_set, in_symbol, allow_inline=True
            )
        pre_value_comments = collect_outer_comments(in_symbol, value_node)

        if pre_value_comments:
            value.before = pre_value_comments + value.before

        trailing_comments = [
            comment
            for comment in outer_comments
            if comment.start_byte >= value_node.end_byte
        ]
        if trailing_comments:
            trailing_comments.sort(key=lambda comment: comment.start_byte)
            trailing_trivia: list[Any] = []
            prev: Node = value_node
            for comment_node in trailing_comments:
                append_gap_between_offsets(trailing_trivia, node, prev, comment_node)
                comment_expr = tree_sitter_node_to_expression(comment_node)
                assert isinstance(comment_expr, Comment)
                if not gap_has_newline_from_offsets(
                    node, prev.end_byte, comment_node.start_byte
                ):
                    comment_expr.inline = True
                trailing_trivia.append(comment_expr)
                prev = comment_node
            value.after.extend(trailing_trivia)

        local_variables: list[Binding | Inherit] = []
        attrpath_order: list[Any] = []
        if binding_set is not None:
            local_variables, _ = parse_binding_sequence(
                node,
                list(binding_set.children),
                initial_trivia=pre_binding_comments,
            )
            if local_variables:
                if post_binding_comments:
                    local_variables[-1].after.extend(post_binding_comments)

                if not pre_binding_comments:
                    if gap_has_empty_line_from_offsets(
                        node,
                        let_symbol.end_byte,
                        binding_set.children[0].start_byte,
                    ):
                        local_variables[0].before.insert(0, empty_line)

                if not post_binding_comments:
                    if gap_has_empty_line_from_offsets(
                        node,
                        binding_set.children[-1].end_byte,
                        in_symbol.start_byte,
                    ):
                        local_variables[-1].after.append(empty_line)
            attrpath_order = _collect_attrpath_order(local_variables)

        if not pre_value_comments:
            if gap_has_empty_line_from_offsets(
                node, in_symbol.end_byte, value_node.start_byte
            ):
                value.before.insert(0, empty_line)

        return cls(
            local_variables=local_variables,
            value=value,
            after_let_comment=after_let_comment,
            attrpath_order=attrpath_order,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2

        before_str = format_trivia(self.before, indent=indent)
        after_str = format_trivia(self.after, indent=indent)
        if self.after and isinstance(self.after[0], Comment) and self.after[0].inline:
            if after_str and not after_str.startswith((" ", "\n")):
                after_str = " " + after_str
        if (
            self.after
            and self.after[-1] not in (linebreak, empty_line)
            and after_str.endswith("\n")
        ):
            after_str = after_str[:-1]
        let_line = " " * indent + "let"
        if self.after_let_comment is not None:
            let_line += f" {self.after_let_comment.rebuild(indent=0)}"

        def ensure_inline_comment_space(body: str, trailing: list[Any]) -> str:
            """Ensure inline trailing comments keep a separating space."""
            if not trailing:
                return body
            first = trailing[0]
            if isinstance(first, Comment) and first.inline:
                comment_str = first.rebuild(indent=0)
                index = None
                if body.endswith(comment_str + "\n"):
                    index = len(body) - len(comment_str) - 1
                elif body.endswith(comment_str):
                    index = len(body) - len(comment_str)
                if index is not None and index > 0 and not body[index - 1].isspace():
                    return f"{body[:index]} {body[index:]}"
            return body

        if not self.local_variables:
            body_str = self.value.rebuild(indent=indent, inline=False)
            body_str = ensure_inline_comment_space(body_str, self.value.after)
            return (
                f"{before_str}"
                + let_line
                + "\n"
                + " " * indent
                + "in\n"
                + body_str
                + f"{after_str}"
            )

        render_values = (
            self.attrpath_order if self.attrpath_order else self.local_variables
        )
        bindings_str = "\n".join(
            _render_bindings(render_values, indent=indented, inline=False)
        )
        binding_suffix = "" if bindings_str.endswith("\n") else "\n"
        body_str = self.value.rebuild(indent=indent, inline=False)
        body_str = ensure_inline_comment_space(body_str, self.value.after)
        return (
            f"{before_str}"
            + let_line
            + f"\n{bindings_str}{binding_suffix}"
            + " " * indent
            + "in\n"
            + body_str
            + f"{after_str}"
        )

    def to_scoped_expression(self) -> NixExpression:
        """Lift let bindings into scope metadata for downstream edits."""
        body_before = list(self.value.before)
        body_after = list(self.value.after)
        if self.after:
            body_after.extend(self.after)
        scope_stack: list[ScopeLayer] = []
        value_state: ScopeState = getattr(self.value, "scope_state", ScopeState())
        if getattr(self.value, "scope", None):
            layer: ScopeLayer = {
                "scope": list(self.value.scope),
                "body_before": list(value_state.body_before),
                "body_after": list(value_state.body_after),
                "attrpath_order": list(value_state.attrpath_order),
                "after_let_comment": value_state.after_let_comment,
            }
            scope_stack.append(layer)
        scope_stack.extend(
            [layer for layer in list(value_state.stack) if layer.get("scope")]
        )
        if not self.local_variables:
            return self.value.model_copy(
                update={
                    "before": body_before,
                    "after": body_after,
                    "scope_state": ScopeState(stack=scope_stack),
                }
            )
        return self.value.model_copy(
            update={
                "before": [],
                "after": [],
                "scope": list(self.local_variables),
                "scope_state": ScopeState(
                    body_before=body_before,
                    body_after=body_after,
                    attrpath_order=list(self.attrpath_order),
                    after_let_comment=self.after_let_comment,
                    stack=scope_stack,
                ),
            }
        )

    def __getitem__(self, key: str):
        """Provide dict-like access to let bindings for editing convenience."""
        for variable in self.local_variables:
            if isinstance(variable, Binding):
                if variable.name == key:
                    return variable.value
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        """Support mutation by key to simplify CLI-driven updates."""
        for i, variable in enumerate(self.local_variables):
            if isinstance(variable, Binding):
                if variable.name == key:
                    variable.value = value
                    return
        self.local_variables.append(Binding(name=key, value=value))

    def __delitem__(self, key: str):
        """Delete by key and error on missing items to avoid silent failures."""
        for i, variable in enumerate(self.local_variables):
            if isinstance(variable, Binding) and variable.name == key:
                del self.local_variables[i]
                return
        raise KeyError(key)


def parse_let_expression(node: Node) -> NixExpression:
    """Expose let parsing as a scope-aware conversion helper."""
    return LetExpression.from_cst(node).to_scoped_expression()


__all__ = ["LetExpression", "parse_let_expression"]
