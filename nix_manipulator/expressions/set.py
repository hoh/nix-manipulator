"""Attribute set parsing and formatting with formatting preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Sequence

from tree_sitter import Node

from nix_manipulator.exceptions import NixSyntaxError
from nix_manipulator.expressions.binding import Binding, _split_attrpath
from nix_manipulator.expressions.binding_parser import parse_binding_sequence
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.scope import Scope
from nix_manipulator.expressions.trivia import (
    apply_trailing_trivia,
    format_trivia,
    gap_has_empty_line_from_offsets,
)
from nix_manipulator.resolution import (
    attach_resolution_context,
    clear_resolution_context,
    scopes_for_owner,
    set_resolution_context,
)


@dataclass(slots=True)
class _AttrpathEntry:
    segments: tuple[str, ...]
    binding: Binding
    before: list[Any] | None = None
    after: list[Any] | None = None


def _merge_attrpath_sets(target: "AttributeSet", incoming: "AttributeSet") -> None:
    """Merge attrpath-derived nested sets while preserving leaf bindings."""
    for item in incoming.values:
        if isinstance(item, Binding):
            existing = next(
                (
                    value
                    for value in target.values
                    if isinstance(value, Binding) and value.name == item.name
                ),
                None,
            )
            if existing is None:
                target.values.append(item)
                continue
            if existing.nested or item.nested:
                if existing.nested and item.nested:
                    if isinstance(existing.value, AttributeSet) and isinstance(
                        item.value, AttributeSet
                    ):
                        _merge_attrpath_sets(existing.value, item.value)
                        continue
                    raise ValueError(f"Duplicate attrpath binding: {item.name}")
                if isinstance(existing.value, AttributeSet) and isinstance(
                    item.value, AttributeSet
                ):
                    target.values.append(item)
                    continue
                raise ValueError(f"Duplicate attrpath binding: {item.name}")
            if isinstance(existing.value, AttributeSet) and isinstance(
                item.value, AttributeSet
            ):
                _merge_attrpath_sets(existing.value, item.value)
                continue
            raise ValueError(f"Duplicate attrpath binding: {item.name}")
        target.values.append(item)


def _merge_attrpath_bindings(
    values: list[Binding | Inherit],
) -> list[Binding | Inherit]:
    """Merge attrpath-derived bindings and reject mixed explicit definitions."""
    merged: list[Binding | Inherit] = []
    first_binding_by_name: dict[str, Binding] = {}
    for item in values:
        if not isinstance(item, Binding):
            merged.append(item)
            continue
        existing = first_binding_by_name.get(item.name)
        if existing is None:
            merged.append(item)
            first_binding_by_name[item.name] = item
            continue
        if existing.nested or item.nested:
            if existing.nested and item.nested:
                if not isinstance(existing.value, AttributeSet) or not isinstance(
                    item.value, AttributeSet
                ):
                    raise ValueError(f"Invalid attrpath binding for: {item.name}")
                _merge_attrpath_sets(existing.value, item.value)
                continue
            if isinstance(existing.value, AttributeSet) and isinstance(
                item.value, AttributeSet
            ):
                merged.append(item)
                continue
            raise ValueError(f"Duplicate attribute definition: {item.name}")
        merged.append(item)
    return merged


def _extract_attrpath_leaf(
    binding: Binding,
) -> tuple[tuple[str, ...], Binding] | None:
    """Return segments and leaf binding for a single attrpath-derived chain."""
    if not binding.nested or not isinstance(binding.value, AttributeSet):
        return None
    segments = [binding.name]
    current = binding.value
    while True:
        bindings = [item for item in current.values if isinstance(item, Binding)]
        if len(bindings) != 1:
            return None
        if any(isinstance(item, Inherit) for item in current.values):
            return None
        child = bindings[0]
        segments.append(child.name)
        if child.nested:
            if not isinstance(child.value, AttributeSet):
                return None
            current = child.value
            continue
        return tuple(segments), child


def _collect_attrpath_order(
    values: list[Binding | Inherit],
) -> list[Binding | Inherit | _AttrpathEntry]:
    """Record the original binding order for attrpath-derived entries."""
    order: list[Binding | Inherit | _AttrpathEntry] = []
    for item in values:
        if isinstance(item, Binding) and item.nested:
            extracted = _extract_attrpath_leaf(item)
            if extracted is not None:
                segments, leaf = extracted
                order.append(
                    _AttrpathEntry(
                        segments=segments,
                        binding=leaf,
                        before=list(item.before),
                        after=list(item.after),
                    )
                )
                continue
        order.append(item)
    return order


def _expand_attrpath_binding(binding: Binding) -> list[Binding]:
    """Flatten a nested attrpath binding into leaf bindings."""
    if not isinstance(binding.value, AttributeSet):
        raise ValueError(f"Attrpath binding missing attrset: {binding.name}")

    flattened: list[Binding] = []

    def walk(prefix: list[str], attrset: AttributeSet) -> None:
        for item in attrset.values:
            if not isinstance(item, Binding):
                raise ValueError("Attrpath binding contains non-binding item")
            if item.nested:
                if not isinstance(item.value, AttributeSet):
                    raise ValueError(f"Attrpath binding missing attrset: {item.name}")
                walk(prefix + [item.name], item.value)
                continue
            full_name = ".".join(prefix + [item.name])
            flattened.append(item.model_copy(update={"name": full_name}))

    walk([binding.name], binding.value)
    return flattened


def _render_bindings(
    values: Sequence[Binding | Inherit | _AttrpathEntry], *, indent: int, inline: bool
) -> list[str]:
    """Render bindings, expanding attrpath-derived trees when needed."""
    rendered: list[str] = []
    for value in values:
        if isinstance(value, _AttrpathEntry):
            before = value.before if value.before is not None else value.binding.before
            after = value.after if value.after is not None else value.binding.after
            binding = value.binding.model_copy(
                update={
                    "name": ".".join(value.segments),
                    "before": list(before),
                    "after": list(after),
                }
            )
            rendered.append(binding.rebuild(indent=indent, inline=inline))
            continue
        if isinstance(value, Binding) and value.nested:
            try:
                expanded = _expand_attrpath_binding(value)
            except ValueError:
                rendered.append(value.rebuild(indent=indent, inline=inline))
                continue
            for item in expanded:
                rendered.append(item.rebuild(indent=indent, inline=inline))
            continue
        rendered.append(value.rebuild(indent=indent, inline=inline))
    return rendered


@dataclass(slots=True, repr=False)
class AttributeSet(TypedExpression):
    """Nix attribute set with trivia-aware formatting."""

    tree_sitter_types: ClassVar[set[str]] = {
        "attrset_expression",
        "rec_attrset_expression",
    }
    values: list[Binding | Inherit]
    multiline: bool = True
    recursive: bool = False
    inner_trivia: list[Any] = field(default_factory=list)
    attrpath_order: list[Binding | Inherit | _AttrpathEntry] = field(
        default_factory=list,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Allow dict initialization to mirror the from_dict helper."""
        NixExpression.__post_init__(self)
        if isinstance(self.values, dict):
            items = list(self.values.items())
            self.values = [Binding(name=key, value=value) for key, value in items]
            if self.multiline and len(items) == 1:
                self.multiline = False

    @classmethod
    def from_dict(
        cls,
        values: dict[
            str,
            NixExpression
            | str
            | int
            | bool
            | float
            | None
            | list[Any]
            | dict[str, Any],
        ],
        *,
        scope: Scope | list[Binding | Inherit] | dict[str, Any] | None = None,
    ):
        """Create a set from Python dicts to ease programmatic edits."""
        values_list: list[Binding | Inherit] = []
        for key, value in values.items():
            values_list.append(Binding(name=key, value=value))
        if scope is None:
            scope_value = Scope()
        elif isinstance(scope, Scope):
            scope_value = scope
        elif isinstance(scope, dict):
            scope_value = Scope(
                [Binding(name=key, value=value) for key, value in scope.items()]
            )
        else:
            scope_value = Scope(scope)
        multiline = len(values_list) != 1
        return cls(values=values_list, scope=scope_value, multiline=multiline)

    @classmethod
    def from_cst(cls, node: Node) -> AttributeSet:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        node_text = node.text
        if node_text is None:
            raise ValueError("Attribute set has no code")

        multiline = b"\n" in node_text
        node_type = getattr(node, "type", None)
        recursive = node_type == "rec_attrset_expression"
        values: list[Binding | Inherit] = []
        inner_trivia: list[Any] = []

        # Flatten content: unwrap `binding_set` if present
        content_nodes: list[Node] = []
        for child in node.named_children:
            if child.type == "binding_set":
                content_nodes.extend(child.named_children)
            else:
                content_nodes.append(child)

        for child in content_nodes:
            if child.type == "ERROR":
                raise NixSyntaxError(f"Code contains ERROR node: {child}")

        values, inner_trivia = parse_binding_sequence(
            node,
            content_nodes,
            open_token="{",
            close_token="}",
        )
        attrpath_order = _collect_attrpath_order(values)
        values = _merge_attrpath_bindings(values)

        if not values and not inner_trivia:
            opening_brace = next(
                (child for child in node.children if child.type == "{"), None
            )
            closing_brace = next(
                (child for child in node.children if child.type == "}"), None
            )
            if opening_brace is not None and closing_brace is not None:
                if gap_has_empty_line_from_offsets(
                    node, opening_brace.end_byte, closing_brace.start_byte
                ):
                    inner_trivia = [empty_line]

        return cls(
            values=values,
            multiline=multiline,
            recursive=recursive,
            inner_trivia=inner_trivia,
            attrpath_order=attrpath_order,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        indented = indent + 2
        prefix = "rec " if self.recursive else ""

        if not self.values:
            if self.inner_trivia:
                before_str = format_trivia(self.before, indent=indent)
                inner_str = format_trivia(self.inner_trivia, indent=indent + 2)
                closing_sep = ""
                if inner_str:
                    closing_sep = "" if inner_str.endswith("\n") else "\n"
                indentation = "" if inline else " " * indent
                set_str = (
                    f"{before_str}{indentation}{prefix}{{\n{inner_str}{closing_sep}"
                    + " " * indent
                    + "}"
                )
                return apply_trailing_trivia(set_str, self.after, indent=indent)
            return self.add_trivia(f"{prefix}{{ }}", indent=indent, inline=inline)

        if self.multiline:
            before_str = format_trivia(self.before, indent=indent)
            render_values = self.attrpath_order if self.attrpath_order else self.values
            bindings_str = "\n".join(
                _render_bindings(render_values, indent=indented, inline=False)
            )
            if bindings_str.endswith("\n"):
                closing_sep = ""
            else:
                closing_sep = "\n"
            indentation = "" if inline else " " * indent
            set_str = (
                f"{before_str}{indentation}{prefix}{{"
                + f"\n{bindings_str}{closing_sep}"
                + " " * indent
                + "}"
            )
            return apply_trailing_trivia(set_str, self.after, indent=indent)
        else:
            render_values = self.attrpath_order if self.attrpath_order else self.values
            bindings_str = " ".join(
                _render_bindings(render_values, indent=indented, inline=True)
            )
            return self.add_trivia(
                f"{prefix}{{ {bindings_str} }}", indent=indent, inline=inline
            )

    def __getitem__(self, key: str):
        """Allow dict-style access for manipulating bindings by name."""
        for binding in self.values:
            if isinstance(binding, Binding) and binding.name == key:
                value = binding.value
                if isinstance(value, NixExpression):
                    attach_resolution_context(value, owner=self)
                return value
        inherit_match = next(
            (
                item
                for item in self.values
                if isinstance(item, Inherit)
                and any(
                    (isinstance(name, Identifier) and name.name == key)
                    or (
                        not isinstance(name, Identifier)
                        and hasattr(name, "value")
                        and name.value == key
                    )
                    for name in item.names
                )
            ),
            None,
        )
        if inherit_match is not None:
            name_expr = next(
                (
                    name
                    for name in inherit_match.names
                    if isinstance(name, Identifier) and name.name == key
                ),
                None,
            )
            target = (
                name_expr.model_copy() if name_expr is not None else Identifier(key)
            )
            self_scope = Scope(self.values, owner=self)
            context_scopes = tuple(list(scopes_for_owner(self)) + [self_scope])
            set_resolution_context(target, context_scopes)
            return target
        try:
            segments = _split_attrpath(key)
        except ValueError:
            raise KeyError(key) from None
        if len(segments) <= 1:
            raise KeyError(key)
        current: AttributeSet = self
        for index, segment in enumerate(segments):
            binding_match: Binding | None = next(
                (
                    item
                    for item in current.values
                    if isinstance(item, Binding) and item.name == segment
                ),
                None,
            )
            if binding_match is None:
                raise KeyError(key)
            if index == len(segments) - 1:
                value = binding_match.value
                if isinstance(value, NixExpression):
                    attach_resolution_context(value, owner=self)
                return value
            if not isinstance(binding_match.value, AttributeSet):
                raise KeyError(key)
            current = binding_match.value
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        """Allow dict-style updates while preserving binding order."""
        if isinstance(value, dict):
            value = AttributeSet.from_dict(value)
        if isinstance(value, NixExpression):
            clear_resolution_context(value)
        for binding in self.values:
            if isinstance(binding, Binding) and binding.name == key:
                binding.value = value
                return
        new_binding = Binding(name=key, value=value)
        self.values.append(new_binding)
        if self.attrpath_order:
            self.attrpath_order.append(new_binding)

    def __delitem__(self, key: str):
        """Delete a binding by key and surface missing keys explicitly."""
        for i, binding in enumerate(self.values):
            if isinstance(binding, Binding) and binding.name == key:
                del self.values[i]
                if self.attrpath_order:
                    for index, item in enumerate(self.attrpath_order):
                        if item is binding:
                            del self.attrpath_order[index]
                            break
                return
        raise KeyError(key)


__all__ = ["AttributeSet"]
