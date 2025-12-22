from __future__ import annotations

import math
from copy import copy
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Self, cast

from tree_sitter import Node

from nix_manipulator.expressions.scope import Scope, ScopeLayer, ScopeState


@dataclass(kw_only=True, slots=True, weakref_slot=True)
class NixExpression:
    """Base class for all Nix objects."""

    before: list[Any] = field(default_factory=list)
    after: list[Any] = field(default_factory=list)
    scope: Scope = field(default_factory=Scope)
    scope_state: ScopeState | dict[str, Any] | None = field(default_factory=ScopeState)

    def __post_init__(self) -> None:
        """Normalize scope containers for dict-style access."""
        if isinstance(self.scope, dict):
            from nix_manipulator.expressions.binding import Binding

            bindings = [
                Binding(name=key, value=value)
                for key, value in self.scope.items()
            ]
            self.scope = Scope(bindings, owner=self)
        elif not isinstance(self.scope, Scope):
            self.scope = Scope(self.scope, owner=self)
        else:
            self.scope.owner = self
        if self.scope_state is None:
            self.scope_state = ScopeState()
        elif isinstance(self.scope_state, dict):
            self.scope_state = ScopeState(**self.scope_state)
        state = cast(ScopeState, self.scope_state)
        if state.stack:
            state.stack = [layer for layer in state.stack if layer.get("scope")]

    @classmethod
    def from_cst(cls, node: Node) -> Self:
        """Construct an object from a CST node."""
        raise NotImplementedError

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct the Nix source code for this object."""
        raise NotImplementedError

    def model_copy(self, update: dict[str, Any] | None = None) -> Self:
        """Copy nodes to enable immutable-style edits during transforms."""
        if not update:
            return copy(self)
        return replace(self, **update)

    @classmethod
    def _fast_construct(cls, **values: Any) -> Self:
        """Construct an instance without extra validation overhead."""
        return cls(**values)

    def add_trivia(
        self,
        rebuild_string: str,
        indent: int,
        inline: bool,
        after_str: str | None = None,
    ) -> str:
        """Centralize trivia handling so all nodes format consistently."""
        from nix_manipulator.expressions.trivia import (
            apply_trailing_trivia, format_trivia, trim_trailing_layout_newline)

        before_str = format_trivia(self.before, indent=indent) if self.before else ""
        indentation = " " * indent if not inline else ""

        rebuilt = f"{before_str}{indentation}{rebuild_string}"

        if after_str is None:
            if not self.after:
                return rebuilt
            return apply_trailing_trivia(rebuilt, self.after, indent=indent)

        after_str = trim_trailing_layout_newline(self.after, after_str)

        return rebuilt + (f"\n{after_str}" if after_str else "")

    def has_scope(self) -> bool:
        """Signal scope metadata so rebuild can wrap in lets when needed."""
        state = cast(ScopeState, self.scope_state)
        return (
            bool(self.scope)
            or any(bool(layer.get("scope")) for layer in state.stack)
        )

    def rebuild_scoped(self, indent: int = 0, inline: bool = False) -> str:
        """Wrap expressions with let-scopes to preserve captured bindings."""
        from nix_manipulator.expressions.let import LetExpression

        layers: list[ScopeLayer] = []
        state = cast(ScopeState, self.scope_state)
        if self.scope:
            layer: ScopeLayer = {
                "scope": list(self.scope),
                "body_before": list(state.body_before),
                "body_after": list(state.body_after),
                "attrpath_order": list(state.attrpath_order),
                "after_let_comment": state.after_let_comment,
            }
            layers.append(layer)
        layers.extend(layer for layer in state.stack if layer.get("scope"))

        body_expr = self.model_copy(
            update={
                "before": list(state.body_before),
                "after": list(state.body_after),
                "scope": [],
                "scope_state": ScopeState(),
            }
        )
        scoped_expr = body_expr
        total_layers = len(layers)
        for index, layer in enumerate(reversed(layers)):
            scoped_expr = scoped_expr.model_copy(
                update={
                    "before": list(layer["body_before"]),
                    "after": list(layer["body_after"]),
                }
            )
            is_outer = index == total_layers - 1
            scoped_expr = LetExpression(
                local_variables=cast(Any, layer["scope"]),
                value=scoped_expr,
                after_let_comment=cast(Any, layer["after_let_comment"]),
                attrpath_order=cast(Any, layer["attrpath_order"]),
                before=self.before if is_outer else [],
                after=self.after if is_outer else [],
            )
        return scoped_expr.rebuild(indent=indent, inline=inline)


class TypedExpression(NixExpression):
    """Base class for all Nix objects matching a tree-sitter type."""

    tree_sitter_types: ClassVar[set[str]]


def coerce_expression(value: Any) -> NixExpression:
    """Convert raw primitive values into NixExpression instances."""
    if isinstance(value, NixExpression):
        return value
    if value is None:
        from nix_manipulator.expressions.primitive import NullPrimitive

        return NullPrimitive()
    if isinstance(value, bool):
        from nix_manipulator.expressions.primitive import Primitive

        return Primitive(value=value)
    if isinstance(value, int):
        from nix_manipulator.expressions.primitive import Primitive

        return Primitive(value=value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Unsupported expression type: float must be finite")
        from nix_manipulator.expressions.float import FloatExpression

        return FloatExpression(value=repr(value))
    if isinstance(value, list):
        from nix_manipulator.expressions.list import NixList

        return NixList(value=value)
    if isinstance(value, str):
        from nix_manipulator.expressions.primitive import Primitive

        return Primitive(value=value)
    raise ValueError(f"Unsupported expression type: {type(value)}")


__all__ = ["NixExpression", "ScopeLayer", "ScopeState", "TypedExpression", "coerce_expression"]
