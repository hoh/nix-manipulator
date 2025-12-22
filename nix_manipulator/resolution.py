"""Resolution helpers for identifier proxies and scope contexts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from weakref import ReferenceType, ref

from nix_manipulator.exceptions import ResolutionError
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.scope import Scope, ScopeLayer


@dataclass(slots=True)
class ResolutionContext:
    """Store the ordered scope chain for resolving identifiers."""

    scopes: tuple[Scope, ...]


_CONTEXTS: dict[int, tuple[ReferenceType[NixExpression], ResolutionContext]] = {}


def _store_context(expr: NixExpression, context: ResolutionContext) -> None:
    """Persist *context* for *expr* and clean up automatically on GC."""

    expr_id = id(expr)

    def _clear(reference: ReferenceType[NixExpression]) -> None:
        existing = _CONTEXTS.get(expr_id)
        if existing is None:
            return
        stored_ref, _ = existing
        if stored_ref is reference:
            _CONTEXTS.pop(expr_id, None)

    _CONTEXTS[expr_id] = (ref(expr, _clear), context)


def _get_context(expr: NixExpression) -> ResolutionContext | None:
    """Return the stored context for *expr*, removing stale entries."""

    entry = _CONTEXTS.get(id(expr))
    if entry is None:
        return None
    stored_ref, context = entry
    if stored_ref() is expr:
        return context
    _CONTEXTS.pop(id(expr), None)
    return None


def _as_scope(value: Scope | Iterable[Any], *, owner: NixExpression | None = None) -> Scope:
    if isinstance(value, Scope):
        if owner is not None:
            value.owner = owner
        return value
    return Scope(value, owner=owner)


def _collect_scopes_from_layers(
    layers: Sequence[ScopeLayer], *, owner: NixExpression | None = None
) -> list[Scope]:
    collected: list[Scope] = []
    for layer in layers:
        scope_value = layer.get("scope", [])
        collected.append(_as_scope(scope_value, owner=owner))
    return collected


def scopes_for_owner(owner: NixExpression) -> tuple[Scope, ...]:
    """Build a scope chain from an owner expression and inherited context (internal helper, not a stable public API)."""
    inherited = _get_context(owner)
    inherited_scopes: tuple[Scope, ...] = ()
    scopes: list[Scope] = []
    if inherited is not None:
        inherited_scopes = inherited.scopes
        scopes.extend(inherited_scopes)

    owner_scopes: list[Scope] = []
    owner_state = getattr(owner, "scope_state", None)
    if getattr(owner, "scope", None) is not None and owner.scope:
        scope_value = _as_scope(owner.scope, owner=owner)
        owner_scopes.append(scope_value)
    if owner_state is not None and owner_state.stack:
        for layer_scope in _collect_scopes_from_layers(
            [layer for layer in owner_state.stack if layer.get("scope")], owner=owner
        ):
            owner_scopes.append(layer_scope)

    if owner_scopes:
        scopes.extend(owner_scopes)

    def _scope_from_attrset(attrset: Any, *, base: tuple[Scope, ...]) -> Scope:
        """Normalize attribute sets into scopes and attach inherited context."""
        scope_value = _as_scope(getattr(attrset, "values", ()), owner=attrset)
        if base:
            set_resolution_context(attrset, base)
        return scope_value

    from nix_manipulator.expressions.set import AttributeSet  # type: ignore

    if isinstance(owner, AttributeSet) and owner.recursive:
        scopes.append(_scope_from_attrset(owner, base=tuple(scopes)))

    from nix_manipulator.expressions.identifier import \
        Identifier  # type: ignore
    from nix_manipulator.expressions.with_statement import \
        WithStatement  # type: ignore

    if isinstance(owner, WithStatement):
        env_scope: Scope | None = None
        environment = owner.environment
        if isinstance(environment, AttributeSet):
            env_scope = _scope_from_attrset(environment, base=tuple(scopes))
        elif isinstance(environment, Identifier):
            context_scopes = tuple(scopes) if scopes else inherited_scopes
            if context_scopes:
                set_resolution_context(environment, context_scopes)
                resolved_env = environment.value
                if isinstance(resolved_env, AttributeSet):
                    env_scope = _scope_from_attrset(resolved_env, base=tuple(scopes))
                else:
                    raise ResolutionError(
                        "with environment must resolve to an attribute set"
                    )
        elif isinstance(environment, Scope):
            env_scope = environment
        else:
            raise ResolutionError(
                "with environment must resolve to an attribute set"
            )
        if env_scope is not None:
            scopes.append(env_scope)

    from nix_manipulator.expressions.function.call import \
        FunctionCall  # type: ignore

    if isinstance(owner, FunctionCall):
        param_scope = function_call_scope(owner, inherited_scopes=tuple(scopes))
        if param_scope is not None:
            scopes.append(param_scope)

    return tuple(scopes)


def function_call_scope(
    call: Any, *, inherited_scopes: tuple[Scope, ...] | None = None
) -> Scope | None:
    """Construct a scope for function parameters when applying a call (internal helper; surface may change)."""
    from nix_manipulator.expressions.binding import Binding  # type: ignore
    from nix_manipulator.expressions.expression import \
        NixExpression  # type: ignore
    from nix_manipulator.expressions.function.call import \
        FunctionCall  # type: ignore
    from nix_manipulator.expressions.function.definition import \
        FunctionDefinition  # type: ignore
    from nix_manipulator.expressions.identifier import \
        Identifier  # type: ignore
    from nix_manipulator.expressions.parenthesis import \
        Parenthesis  # type: ignore
    from nix_manipulator.expressions.set import AttributeSet  # type: ignore

    if not isinstance(call, FunctionCall):
        return None
    function_expr = call.name
    if isinstance(function_expr, Parenthesis):
        function_expr = function_expr.value
    if not isinstance(function_expr, FunctionDefinition):
        return None
    parameters = function_expr.argument_set
    base_scopes: tuple[Scope, ...] = tuple(inherited_scopes or ())

    if not base_scopes:
        call_state = getattr(call, "scope_state", None)
        call_scopes: list[Scope] = []
        if getattr(call, "scope", None) is not None and call.scope:
            call_scope = _as_scope(getattr(call, "scope"), owner=call)
            call_scopes.append(call_scope)
        if call_state is not None and call_state.stack:
            call_scopes.extend(
                _collect_scopes_from_layers(
                    [layer for layer in call_state.stack if layer.get("scope")],
                    owner=call,
                )
            )
        base_scopes = tuple(call_scopes)

    def _resolve_argument_to_attrset(argument: Any, *, scope_chain: tuple[Scope, ...]) -> AttributeSet:
        """Accept identifiers/parentheses that resolve to attrsets."""
        if argument is None:
            raise ResolutionError("Function call requires an attribute set argument")

        resolved = argument
        while isinstance(resolved, Parenthesis):
            resolved = resolved.value

        if isinstance(resolved, Identifier):
            if scope_chain:
                set_resolution_context(resolved, scope_chain)
            resolved = resolved.value

        if isinstance(resolved, AttributeSet):
            return resolved

        raise ResolutionError("Function call requires an attribute set argument")

    param_scope = Scope(owner=call)

    if isinstance(parameters, list):
        params_iterable = parameters
        resolved_argument = _resolve_argument_to_attrset(
            call.argument, scope_chain=base_scopes
        )
        provided_scope = _as_scope(resolved_argument.values, owner=resolved_argument)

        for param in params_iterable:
            if not isinstance(param, Identifier):
                continue
            try:
                binding = provided_scope.get_binding(param.name)
                param_scope.append(binding)
                continue
            except KeyError:
                pass

            default_value = param.default_value
            if default_value is not None:
                param_scope.append(Binding(name=param.name, value=default_value))
                continue
            raise ResolutionError(f"Missing value for function parameter: {param.name}")
    elif isinstance(parameters, Identifier):
        if call.argument is None:
            raise ResolutionError(
                f"Missing value for function parameter: {parameters.name}"
            )
        arg_value = call.argument
        if isinstance(arg_value, Parenthesis):
            arg_value = arg_value.value
        if isinstance(arg_value, Identifier) and base_scopes:
            set_resolution_context(arg_value, base_scopes)
            arg_value = arg_value.value
        param_scope.append(Binding(name=parameters.name, value=arg_value))
    else:
        return None

    scope_chain = tuple(list(base_scopes) + [param_scope])
    for item in param_scope:
        if isinstance(item, Binding) and isinstance(item.value, NixExpression):
            set_resolution_context(item.value, scope_chain)
    return param_scope


def attach_resolution_context(expr: NixExpression, *, owner: NixExpression | None = None) -> NixExpression:
    """Attach a scope chain to *expr* so Identifier.value can resolve bindings (internal helper).

    The chain is derived from the owner's scopes and any previously inherited
    context. If no scopes are available, the expression is returned unchanged.
    """

    scopes: tuple[Scope, ...] | None = None
    if owner is not None:
        scopes = scopes_for_owner(owner)
    else:
        inherited = _get_context(expr)
        if inherited is not None:
            scopes = inherited.scopes

    if scopes:
        _store_context(expr, ResolutionContext(scopes=scopes))
    return expr


def set_resolution_context(expr: NixExpression, scopes: Iterable[Scope]) -> None:
    """Set an explicit scope chain on *expr* (internal helper; not a stable API)."""

    scopes_tuple = tuple(scopes)
    if not scopes_tuple:
        return
    _store_context(expr, ResolutionContext(scopes=scopes_tuple))


def clear_resolution_context(expr: NixExpression) -> None:
    """Remove any stored scope chain for *expr* (internal helper)."""

    _CONTEXTS.pop(id(expr), None)


def get_resolution_context(expr: NixExpression) -> ResolutionContext | None:
    """Retrieve the context attached to an expression, if any (internal helper)."""

    return _get_context(expr)


__all__ = [
    "ResolutionContext",
    "attach_resolution_context",
    "set_resolution_context",
    "clear_resolution_context",
    "get_resolution_context",
    "scopes_for_owner",
    "function_call_scope",
]
