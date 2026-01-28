from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Node

from nix_manipulator.exceptions import ResolutionError
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    coerce_expression)
from nix_manipulator.expressions.scope import Scope
from nix_manipulator.expressions.trivia import trim_leading_layout_trivia
from nix_manipulator.resolution import (get_resolution_context,
                                        set_resolution_context)


@dataclass(slots=True, repr=False)
class Identifier(NixExpression):
    name: str
    default_value: NixExpression | None = None
    default_value_on_newline: bool = False
    default_value_indent: int | None = None
    after_question: list[Comment] = field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node, before: list[Any] | None = None):
        """Retain original identifier text for stable symbol references."""
        if node.text is None:
            raise ValueError("Identifier has no name")
        name = node.text.decode()
        return cls(name=name, before=before or [])

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        target = self
        if not inline and indent == 0:
            trimmed_before = trim_leading_layout_trivia(self.before)
            if trimmed_before and trimmed_before != self.before:
                target = self.model_copy(update={"before": trimmed_before})

        comma = "," if trailing_comma else ""
        if self.default_value is not None:
            after_question = ""
            if self.after_question:
                after_question = " " + " ".join(
                    comment.rebuild(indent=0) for comment in self.after_question
                )
            if self.default_value_on_newline:
                value_indent = (
                    self.default_value_indent
                    if self.default_value_indent is not None
                    else indent + 2
                )
                value_str = self.default_value.rebuild(
                    indent=value_indent, inline=False
                )
                return target.add_trivia(
                    f"{self.name} ?{after_question}\n{value_str}{comma}",
                    indent,
                    inline,
                )
            return target.add_trivia(
                f"{self.name} ?{after_question} {self.default_value.rebuild(indent=indent, inline=True)}{comma}",
                indent,
                inline,
                )
        else:
            return target.add_trivia(f"{self.name}{comma}", indent, inline)

    @property
    def value(self) -> NixExpression:
        """Resolve the identifier to the defining binding's value."""
        context = get_resolution_context(self)
        if context is None:
            raise ResolutionError(
                f"Cannot resolve identifier without scope context: {self.name}"
            )
        resolved, _ = _resolve_identifier(self, context.scopes)
        return resolved

    @value.setter
    def value(self, new_value: Any) -> None:
        """Assign through the identifier to the defining binding."""
        context = get_resolution_context(self)
        if context is None:
            raise ResolutionError(
                f"Cannot resolve identifier without scope context: {self.name}"
            )

        _resolved, binding = _resolve_identifier(self, context.scopes)
        if not isinstance(new_value, NixExpression):
            new_expr = coerce_expression(new_value)
        else:
            new_expr = new_value

        if isinstance(binding.value, NixExpression):
            before = binding.value.before if not new_expr.before else new_expr.before
            after = binding.value.after if not new_expr.after else new_expr.after
            new_expr = new_expr.model_copy(
                update={"before": list(before), "after": list(after)}
            )

        binding.value = new_expr
        if isinstance(new_expr, NixExpression):
            set_resolution_context(new_expr, context.scopes)


def _resolve_identifier(
    identifier: "Identifier",
    scopes: tuple[Scope, ...],
    visited: set[int] | None = None,
    inherit_visited: set[int] | None = None,
) -> tuple[NixExpression, Binding]:
    """Resolve an identifier across the provided scope chain."""

    visited = visited or set()
    inherit_visited = inherit_visited or set()
    ordered_scopes = [scope for scope in reversed(scopes) if isinstance(scope, Scope)]
    total_scopes = len(ordered_scopes)

    def _resolve_binding(binding: Binding, scope_chain: tuple[Scope, ...]) -> tuple[NixExpression, Binding]:
        if id(binding) in visited:
            raise ResolutionError(
                f"Cyclic reference detected while resolving {identifier.name}"
            )
        visited.add(id(binding))
        value = binding.value
        if not isinstance(value, NixExpression):
            value = coerce_expression(value)
            binding.value = value

        set_resolution_context(value, scope_chain)
        if isinstance(value, Identifier):
            return _resolve_identifier(value, scope_chain, visited, inherit_visited)
        return value, binding

    def _inherit_matches(target: str, inherit_expr: Any) -> bool:
        from nix_manipulator.expressions.inherit import Inherit  # type: ignore

        if not isinstance(inherit_expr, Inherit):
            return False
        for name_expr in inherit_expr.names:
            if isinstance(name_expr, Identifier) and name_expr.name == target:
                return True
            if not isinstance(name_expr, Identifier) and hasattr(name_expr, "value") and name_expr.value == target:
                return True
        return False

    def _resolve_inherited_binding(
        inherit_expr: Any,
        scope_chain: tuple[Scope, ...],
        outer_chain: tuple[Scope, ...],
    ) -> tuple[NixExpression, Binding]:
        if id(inherit_expr) in inherit_visited:
            raise ResolutionError(
                f"Cyclic inherit detected while resolving {identifier.name}"
            )
        inherit_visited.add(id(inherit_expr))

        from_expression = getattr(inherit_expr, "from_expression", None)
        if from_expression is None:
            if not outer_chain:
                raise ResolutionError(f"Unbound identifier: {identifier.name}")
            return _resolve_identifier(
                identifier,
                outer_chain,
                visited,
                inherit_visited,
            )

        source = from_expression
        if isinstance(from_expression, Identifier):
            set_resolution_context(from_expression, scope_chain)
            source = from_expression.value

        if isinstance(source, Scope):
            new_chain = tuple(list(scope_chain) + [source])
            return _resolve_identifier(
                identifier,
                new_chain,
                visited,
                inherit_visited,
            )

        if hasattr(source, "values"):
            attr_scope = Scope(getattr(source, "values", ()), owner=source)
            new_chain = tuple(list(scope_chain) + [attr_scope])
            if isinstance(source, NixExpression):
                set_resolution_context(source, new_chain)
            return _resolve_identifier(
                identifier,
                new_chain,
                visited,
                inherit_visited,
            )

        raise ResolutionError(
            f"Inherited expression does not expose attributes: {identifier.name}"
        )

    for index, scope in enumerate(ordered_scopes):
        scope_chain = tuple(reversed(ordered_scopes[index:]))
        outer_chain = tuple(reversed(ordered_scopes[index + 1 :])) if index + 1 < total_scopes else ()
        try:
            binding = scope.get_binding(identifier.name)
            return _resolve_binding(binding, scope_chain)
        except KeyError:
            quoted_match = next(
                (
                    entry
                    for entry in scope
                    if isinstance(entry, Binding)
                    and isinstance(entry.name, str)
                    and entry.name.strip('"') == identifier.name
                ),
                None,
            )
            if quoted_match is not None:
                return _resolve_binding(quoted_match, scope_chain)

        for entry in scope:
            if not _inherit_matches(identifier.name, entry):
                continue
            return _resolve_inherited_binding(entry, scope_chain, outer_chain)

    raise ResolutionError(f"Unbound identifier: {identifier.name}")


__all__ = ["Identifier"]
