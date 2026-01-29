"""Scope container for let-bound bindings with dict-style access."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    SupportsIndex,
    TypeAlias,
    TypedDict,
    cast,
)

if TYPE_CHECKING:
    from nix_manipulator.expressions.binding import Binding
    from nix_manipulator.expressions.comment import Comment
    from nix_manipulator.expressions.expression import NixExpression
    from nix_manipulator.expressions.inherit import Inherit
    from nix_manipulator.expressions.set import _AttrpathEntry

    ScopeItem: TypeAlias = Binding | Inherit
    AttrpathOrderItem: TypeAlias = Binding | Inherit | _AttrpathEntry
else:
    ScopeItem = Any  # type: ignore[assignment]
    AttrpathOrderItem = Any  # type: ignore[assignment]


class Scope(list[Any]):
    """List-like scope bindings with dict-style access by name."""

    owner: "NixExpression | None"

    def __init__(
        self, items: Iterable[Any] = (), *, owner: "NixExpression | None" = None
    ) -> None:
        super().__init__(items)
        self.owner: "NixExpression | None" = owner

    def _find_binding_index(self, key: str) -> int | None:
        from nix_manipulator.expressions.binding import Binding

        for index, item in enumerate(self):
            if isinstance(item, Binding) and item.name == key:
                return index
        return None

    def __getitem__(self, key: SupportsIndex | slice | str) -> Any:
        if isinstance(key, str):
            binding = self.get_binding(key)
            value = binding.value
            from nix_manipulator.expressions.expression import NixExpression

            if isinstance(value, NixExpression):
                from nix_manipulator.resolution import attach_resolution_context

                if self.owner is not None:
                    attach_resolution_context(value, owner=self.owner)
            return value
        return super().__getitem__(key)

    def get_binding(self, key: str):
        """Return the binding for *key* or raise KeyError if missing."""
        index = self._find_binding_index(key)
        if index is None:
            raise KeyError(key)
        binding = super().__getitem__(index)
        from nix_manipulator.expressions.binding import Binding

        return cast(Binding, binding)

    def __setitem__(self, key: SupportsIndex | slice | str, value: Any) -> None:
        if isinstance(key, str):
            if isinstance(value, dict):
                from nix_manipulator.expressions.set import AttributeSet

                value = AttributeSet.from_dict(value)
            from nix_manipulator.expressions.expression import NixExpression

            if isinstance(value, NixExpression):
                from nix_manipulator.resolution import clear_resolution_context

                clear_resolution_context(value)
            index = self._find_binding_index(key)
            if index is None:
                from nix_manipulator.expressions.binding import Binding

                self.append(Binding(name=key, value=value))
            else:
                super().__getitem__(index).value = value
            return
        super().__setitem__(key, value)

    def __delitem__(self, key: SupportsIndex | slice | str) -> None:
        if isinstance(key, str):
            index = self._find_binding_index(key)
            if index is None:
                raise KeyError(key)
            super().__delitem__(index)
            return
        super().__delitem__(key)


class ScopeLayer(TypedDict):
    """Persistable let/with layer so automated edits can rewrap code exactly.

    Capturing bindings plus surrounding trivia lets the CLI rebuild RFC-166
    compliant scopes without losing comments or attrpath order, which keeps
    large Nix estates safely auto-updatable.
    """

    scope: Scope | list[ScopeItem]
    body_before: list[Any]
    body_after: list[Any]
    attrpath_order: list[AttrpathOrderItem]
    after_let_comment: Comment | None


@dataclass(slots=True)
class ScopeState:
    """Mutable scratchpad for scope layering during transformations.

    Holding pending body trivia and stacked scope layers outside the core
    expression API lets tools stage complex rewrites while keeping signatures
    simple, reducing risk of format drift in production Nix configs.
    """

    body_before: list[Any] = field(default_factory=list)
    body_after: list[Any] = field(default_factory=list)
    attrpath_order: list[AttrpathOrderItem] = field(default_factory=list)
    after_let_comment: Comment | None = None
    stack: list[ScopeLayer] = field(default_factory=list)


__all__ = ["Scope", "ScopeLayer", "ScopeState"]
