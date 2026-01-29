import re
from dataclasses import dataclass
from typing import Sequence, cast

from nix_manipulator.exceptions import ResolutionError
from nix_manipulator.expressions import (
    AttributeSet,
    Binding,
    FunctionCall,
    FunctionDefinition,
    Identifier,
    Inherit,
    NixExpression,
    NixSourceCode,
    Scope,
    WithStatement,
)
from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.primitive import _escape_nix_string
from nix_manipulator.expressions.raw import RawExpression
from nix_manipulator.expressions.scope import ScopeLayer, ScopeState
from nix_manipulator.expressions.set import _AttrpathEntry
from nix_manipulator.parser import parse
from nix_manipulator.resolution import (
    attach_resolution_context,
    scopes_for_owner,
    set_resolution_context,
)


def _resolve_target_set_from_expr(
    target: NixExpression,
    *,
    scope_chain: tuple[Scope, ...] | None = None,
    _visited: set[int] | None = None,
) -> AttributeSet:
    """Find the editable attribute set so CLI edits land in the expected scope."""
    visited = _visited or set()
    if id(target) in visited:
        raise ValueError("Unexpected expression type")
    visited.add(id(target))

    def _resolve_nested(
        expr: NixExpression, *, scopes: tuple[Scope, ...] | None = scope_chain
    ) -> AttributeSet:
        return _resolve_target_set_from_expr(expr, scope_chain=scopes, _visited=visited)

    if scope_chain is None:
        scope_chain = scopes_for_owner(target)

    match target:
        case Assertion():
            if target.body is None:
                raise ValueError("Unexpected assertion without body")
            return _resolve_nested(target.body)
        case LetExpression():
            return _resolve_nested(target.value)
        case FunctionDefinition():
            output = target.output
            if isinstance(output, FunctionCall) and isinstance(
                output.argument, AttributeSet
            ):
                return output.argument
            if isinstance(output, AttributeSet):
                return output
            if output is None:
                raise ValueError("Unexpected function output type")
            try:
                return _resolve_nested(output)
            except ValueError as exc:
                raise ValueError("Unexpected function output type") from exc
        case WithStatement():
            body_scopes = scopes_for_owner(target) or scope_chain
            attach_resolution_context(target.body, owner=target)
            return _resolve_target_set_from_expr(
                target.body,
                scope_chain=body_scopes,
                _visited=visited,
            )
        case Identifier():
            identifier_scopes = scope_chain or scopes_for_owner(target)
            if identifier_scopes:
                set_resolution_context(target, identifier_scopes)
            resolved = target.value
            return _resolve_nested(resolved, scopes=identifier_scopes)
        case Parenthesis():
            return _resolve_nested(target.value)
        case AttributeSet():
            return target
        case FunctionCall():
            callee = target.name
            while isinstance(callee, Parenthesis):
                callee = callee.value
            if isinstance(callee, (FunctionDefinition, Identifier)) and isinstance(
                target.argument, AttributeSet
            ):
                return target.argument
            raise ValueError("Unexpected expression type")
        case _:
            raise ValueError("Unexpected expression type")


def _resolve_target_set(source: NixSourceCode) -> AttributeSet:
    """Require a single top-level target to keep edits deterministic (internal CLI helper)."""
    if not source.expressions:
        raise ValueError("Source contains no expressions")
    if len(source.expressions) != 1:
        raise ValueError("Source must contain exactly one top-level expression")
    top_level = source.expressions[0]
    if not isinstance(
        top_level,
        (
            Assertion,
            FunctionDefinition,
            AttributeSet,
            WithStatement,
            Identifier,
            Parenthesis,
            LetExpression,
            FunctionCall,
        ),
    ):
        raise ValueError(
            "Top-level expression must be an attribute set or function definition"
        )
    try:
        return _resolve_target_set_from_expr(top_level)
    except ValueError as exc:
        raise ValueError(
            "Top-level expression must be an attribute set or function definition"
        ) from exc


@dataclass(frozen=True)
class _NPathSegment:
    name: str
    quoted: bool


_NPATH_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")


def _parse_npath(npath: str) -> list[_NPathSegment]:
    """Parse a dot-delimited NPath with optional quoted segments."""
    if not npath:
        raise ValueError("NPath cannot be empty")

    segments: list[_NPathSegment] = []
    buffer: list[str] = []
    in_quotes = False
    quoted_segment = False
    escape = False

    def finalize_segment() -> None:
        nonlocal buffer, quoted_segment
        name = "".join(buffer)
        if not quoted_segment and name == "":
            raise ValueError("NPath contains an empty segment")
        if not quoted_segment and name and not _NPATH_IDENTIFIER_RE.match(name):
            raise ValueError(f"NPath segment is not a valid identifier: {name}")
        segments.append(_NPathSegment(name=name, quoted=quoted_segment))
        buffer = []
        quoted_segment = False

    for ch in npath:
        if in_quotes:
            if escape:
                if ch == "n":
                    buffer.append("\n")
                elif ch == "r":
                    buffer.append("\r")
                elif ch == "t":
                    buffer.append("\t")
                elif ch in ('"', "\\"):
                    buffer.append(ch)
                else:
                    buffer.append("\\" + ch)
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_quotes = False
                quoted_segment = True
                continue
            buffer.append(ch)
            continue

        if ch == ".":
            finalize_segment()
            continue
        if ch == '"':
            if buffer:
                raise ValueError(
                    "Quoted NPath segments must start at the segment boundary"
                )
            in_quotes = True
            continue
        buffer.append(ch)

    if escape:
        raise ValueError("NPath contains a dangling escape sequence")
    if in_quotes:
        raise ValueError("NPath contains an unterminated quoted segment")

    finalize_segment()
    return segments


def _format_attr_name(segment: _NPathSegment) -> str:
    """Format a segment as a binding name, quoting when needed."""
    if segment.quoted or not _NPATH_IDENTIFIER_RE.match(segment.name):
        escaped = _escape_nix_string(segment.name, escape_interpolation=True)
        return f'"{escaped}"'
    return segment.name


def _format_npath_segments(npath: str) -> list[str]:
    """Parse an NPath into formatted binding-name segments."""
    return [_format_attr_name(segment) for segment in _parse_npath(npath)]


@dataclass(frozen=True)
class _ResolvedNPath:
    target_set: AttributeSet
    segments: list[str]
    attrpath_leaf: Binding | None
    attrpath_root: Binding | None


def _resolve_npath(source: NixSourceCode, npath: str) -> _ResolvedNPath:
    """Normalize NPath input into formatted segments and attrpath metadata."""
    target_set = _resolve_target_set(source)
    segments = _format_npath_segments(npath)
    if not segments:
        raise ValueError("NPath cannot be empty")
    attrpath_leaf = _find_attrpath_leaf(target_set, segments)
    attrpath_root = _find_attrpath_root(target_set, segments[0])
    return _ResolvedNPath(
        target_set=target_set,
        segments=segments,
        attrpath_leaf=attrpath_leaf,
        attrpath_root=attrpath_root,
    )


def _find_binding(target_set: AttributeSet, key: str) -> Binding | None:
    """Find the first binding with a matching name."""
    return next(
        (
            binding
            for binding in target_set.values
            if isinstance(binding, Binding) and binding.name == key
        ),
        None,
    )


def _find_named_binding(
    values: Sequence[NixExpression], key: str, *, nested: bool | None = None
) -> Binding | None:
    """Find a binding by name, optionally filtering on nested flag."""
    for item in values:
        if not isinstance(item, Binding) or item.name != key:
            continue
        if nested is None or item.nested == nested:
            return item
    return None


def _find_attrpath_leaf(
    target_set: AttributeSet, segments: list[str]
) -> Binding | None:
    """Locate an attrpath-derived binding by its full path."""
    stack = _walk_attrpath_stack(
        target_set, segments, leaf_nested=False, require_root=False
    )
    if stack is None:
        return None
    return stack[-1][1]


def _find_attrpath_root(target_set: AttributeSet, root: str) -> Binding | None:
    """Locate the root binding for attrpath-derived entries."""
    for item in target_set.values:
        if isinstance(item, Binding) and item.nested and item.name == root:
            return item
    return None


def _path_exists_in_attrset(target_set: AttributeSet, segments: list[str]) -> bool:
    """Check whether an NPath already resolves to a concrete binding."""
    if not segments:
        return False

    if _find_attrpath_leaf(target_set, segments) is not None:
        return True

    current = target_set
    for index, segment in enumerate(segments):
        binding = _find_named_binding(current.values, segment, nested=False)
        if binding is None:
            return False
        is_leaf = index == len(segments) - 1
        if is_leaf:
            return True
        if not isinstance(binding.value, AttributeSet):
            return False
        current = binding.value
    return False


def _walk_attrpath_stack(
    target_set: AttributeSet,
    segments: list[str],
    *,
    leaf_nested: bool,
    require_root: bool,
) -> list[tuple[AttributeSet, Binding]] | None:
    """Walk attrpath segments and return the parent stack."""
    if len(segments) < 2:
        if require_root:
            raise KeyError(segments[0] if segments else "")
        return None
    root = _find_attrpath_root(target_set, segments[0])
    if root is None or not isinstance(root.value, AttributeSet):
        if require_root:
            raise KeyError(segments[0])
        return None

    current = root.value
    stack: list[tuple[AttributeSet, Binding]] = [(target_set, root)]
    for index, segment in enumerate(segments[1:], start=1):
        is_leaf = index == len(segments) - 1
        nested = leaf_nested if is_leaf else True
        binding = _find_named_binding(current.values, segment, nested=nested)
        if binding is None:
            if require_root:
                raise KeyError(segment)
            return None
        stack.append((current, binding))
        if is_leaf:
            break
        if not isinstance(binding.value, AttributeSet):
            if require_root:
                raise ValueError(
                    f"NPath segment does not point to an attribute set: {segment}"
                )
            return None
        current = binding.value
    return stack


def _set_attrpath_value(
    target_set: AttributeSet,
    root: Binding,
    segments: list[str],
    value_expr: NixExpression,
) -> None:
    """Create or update an attrpath-derived leaf binding under a root."""
    if not isinstance(root.value, AttributeSet):
        raise ValueError("Attrpath root does not point to an attribute set")
    full_segments = tuple(segments)
    current = root.value
    for seg in segments[1:-1]:
        binding = _find_named_binding(current.values, seg, nested=True)
        if binding is None:
            if _find_named_binding(current.values, seg, nested=False) is not None:
                raise ValueError(f"Mixed explicit binding inside attrpath: {seg}")
            nested_set = AttributeSet(values=[], multiline=current.multiline)
            binding = Binding(name=seg, value=nested_set, nested=True)
            current.values.append(binding)
        if not binding.nested:
            raise ValueError(f"Mixed explicit binding inside attrpath: {seg}")
        if not isinstance(binding.value, AttributeSet):
            raise ValueError(f"NPath segment does not point to an attribute set: {seg}")
        current = binding.value

    final_key = segments[-1]
    if _find_named_binding(current.values, final_key, nested=True) is not None:
        raise ValueError(f"Mixed explicit binding inside attrpath: {final_key}")
    binding = _find_named_binding(current.values, final_key, nested=False)
    if binding is not None:
        binding.value = value_expr
        return
    new_binding = Binding(
        name=final_key,
        value=value_expr,
    )
    current.values.append(new_binding)
    if target_set.attrpath_order:
        target_set.attrpath_order.append(
            _AttrpathEntry(segments=full_segments, binding=new_binding)
        )


def _remove_attrpath_value(target_set: AttributeSet, segments: list[str]) -> None:
    """Remove an attrpath-derived leaf binding and prune empty nodes."""
    stack = _walk_attrpath_stack(
        target_set, segments, leaf_nested=False, require_root=True
    )
    assert stack is not None
    parent_set, leaf_binding = stack[-1]
    parent_set.values.remove(leaf_binding)
    if target_set.attrpath_order:
        for index, item in enumerate(target_set.attrpath_order):
            if isinstance(item, _AttrpathEntry) and item.binding is leaf_binding:
                del target_set.attrpath_order[index]
                break

    for parent_set, binding in reversed(stack[:-1]):
        if isinstance(binding.value, AttributeSet) and not binding.value.values:
            parent_set.values.remove(binding)
        else:
            break


def _resolve_npath_parent(
    target_set: AttributeSet, npath: str, *, create_missing: bool
) -> tuple[AttributeSet, str]:
    """Resolve or create the parent attribute set for an NPath."""
    segments = _parse_npath(npath)
    if not segments:
        raise ValueError("NPath cannot be empty")

    current = target_set
    for segment in segments[:-1]:
        key = _format_attr_name(segment)
        try:
            value = current[key]
        except KeyError:
            if not create_missing:
                raise KeyError(f"NPath segment not found: {segment.name}") from None
            nested = AttributeSet(values=[], multiline=current.multiline)
            current[key] = nested
            current = nested
            continue
        if not isinstance(value, AttributeSet):
            raise ValueError(
                f"NPath segment does not point to an attribute set: {segment.name}"
            )
        current = value

    final_key = _format_attr_name(segments[-1])
    return current, final_key


def _segment_name(segment: str) -> str:
    """Strip quotes from formatted segment names."""
    if segment.startswith('"') and segment.endswith('"'):
        return segment[1:-1]
    return segment


def _resolve_inherited_binding(
    target_set: AttributeSet,
    *,
    root_key: str,
    leaf_key: str,
    outer_bindings: Sequence[Binding] | None = None,
) -> Binding | None:
    """Follow inherit entries inside function-call attrsets to a real binding."""
    root_binding = _find_binding(target_set, root_key)
    if root_binding is None:
        return None
    value = root_binding.value
    if not isinstance(value, FunctionCall):
        return None
    argument = value.argument
    if not isinstance(argument, AttributeSet):
        return None
    for item in argument.values:
        if not isinstance(item, Inherit):
            continue
        for name_expr in item.names:
            name: str | None = None
            if isinstance(name_expr, Identifier):
                name = name_expr.name
            elif hasattr(name_expr, "value"):
                name = getattr(name_expr, "value", None)
            if name != leaf_key:
                continue
            bound = _find_binding(target_set, leaf_key)
            if bound is not None:
                return bound
            if outer_bindings:
                for outer in outer_bindings:
                    if outer.name == leaf_key:
                        return outer
    return None


def _set_value_in_attrset(
    target_set: AttributeSet,
    npath: str,
    value_expr: NixExpression,
    *,
    let_bindings: Sequence[Binding] | None = None,
) -> None:
    """Apply set-value semantics to an AttributeSet without rebuilding."""
    segments = _format_npath_segments(npath)
    if not segments:
        raise ValueError("NPath cannot be empty")

    def _assign_through_identifier(identifier: Identifier) -> bool:
        """Try to write via identifier resolution contexts instead of overwriting."""
        scopes = scopes_for_owner(target_set)
        if scopes:
            set_resolution_context(identifier, scopes)
            try:
                identifier.value = value_expr
                return True
            except ResolutionError:
                return False
        return False

    attrpath_leaf = _find_attrpath_leaf(target_set, segments)
    attrpath_root = _find_attrpath_root(target_set, segments[0])
    if attrpath_leaf is not None:
        attrpath_leaf.value = value_expr
        return

    if len(segments) == 1:
        key = segments[0]
        if attrpath_root is not None:
            raise ValueError(f"Cannot overwrite attrpath-derived binding: {key}")
        binding = _find_binding(target_set, key)
        if binding is not None:
            if isinstance(binding.value, Identifier):
                if _assign_through_identifier(binding.value):
                    return
                target_name = binding.value.name
                if let_bindings:
                    for outer in let_bindings:
                        if outer.name == target_name:
                            outer.value = value_expr
                            return
                sibling_binding = _find_binding(target_set, target_name)
                if sibling_binding is not None:
                    sibling_binding.value = value_expr
                    return
            binding.value = value_expr
            return
        target_set[key] = value_expr
        return

    if attrpath_root is not None:
        _set_attrpath_value(target_set, attrpath_root, segments, value_expr)
        return

    try:
        parent_set, final_key = _resolve_npath_parent(
            target_set, npath, create_missing=True
        )
    except ValueError:
        if len(segments) >= 2:
            root_key = _segment_name(segments[-2])
            leaf_key = _segment_name(segments[-1])
            inherited_binding = _resolve_inherited_binding(
                target_set,
                root_key=root_key,
                leaf_key=leaf_key,
                outer_bindings=let_bindings,
            )
            if inherited_binding is not None:
                if isinstance(inherited_binding.value, Identifier) and let_bindings:
                    for outer in let_bindings:
                        if outer.name == inherited_binding.value.name:
                            outer.value = value_expr
                            return
                inherited_binding.value = value_expr
                return
        raise
    existing_binding = _find_binding(parent_set, final_key)
    if existing_binding is not None:
        if isinstance(existing_binding.value, Identifier):
            if _assign_through_identifier(existing_binding.value):
                return
            target_name = existing_binding.value.name
            if let_bindings:
                for outer in let_bindings:
                    if outer.name == target_name:
                        outer.value = value_expr
                        return
            sibling_binding = _find_binding(parent_set, target_name)
            if sibling_binding is not None:
                sibling_binding.value = value_expr
                return
        existing_binding.value = value_expr
        return
    parent_set[final_key] = value_expr


def _remove_value_in_attrset(target_set: AttributeSet, npath: str) -> None:
    """Apply remove-value semantics to an AttributeSet without rebuilding."""
    segments = _format_npath_segments(npath)
    if not segments:
        raise ValueError("NPath cannot be empty")

    attrpath_leaf = _find_attrpath_leaf(target_set, segments)
    attrpath_root = _find_attrpath_root(target_set, segments[0])
    if attrpath_leaf is not None:
        _remove_attrpath_value(target_set, segments)
        return

    if len(segments) == 1:
        key = segments[0]
        if attrpath_root is not None:
            raise KeyError(key)
        binding = _find_binding(target_set, key)
        if binding is None:
            raise KeyError(key)
        del target_set[key]
        return

    if attrpath_root is not None:
        _remove_attrpath_value(target_set, segments)
        return

    parent_set, final_key = _resolve_npath_parent(
        target_set, npath, create_missing=False
    )
    del parent_set[final_key]


def _split_scope_npath(npath: str) -> tuple[int, str] | None:
    """Detect leading @-scope selectors and return (depth, remaining path)."""
    depth = 0
    for ch in npath:
        if ch != "@":
            break
        depth += 1
    if depth == 0:
        return None
    remainder = npath[depth:]
    if not remainder:
        raise ValueError("Scope path is missing a binding name")
    return depth, remainder


def _collect_scope_layers(expr: NixExpression) -> list[ScopeLayer]:
    """Return ordered scope layers (outermost → innermost) for editing (internal CLI helper)."""
    layers: list[ScopeLayer] = []
    state = cast(ScopeState, expr.scope_state)
    if expr.scope:
        layer: ScopeLayer = {
            "scope": expr.scope,
            "body_before": list(state.body_before),
            "body_after": list(state.body_after),
            "attrpath_order": list(state.attrpath_order),
            "after_let_comment": state.after_let_comment,
        }
        layers.append(layer)
    for layer in state.stack:
        scope_value = layer.get("scope")
        if not scope_value:
            continue
        layer_dict: ScopeLayer = {
            "scope": scope_value,
            "body_before": list(layer["body_before"]),
            "body_after": list(layer["body_after"]),
            "attrpath_order": list(layer["attrpath_order"]),
            "after_let_comment": layer["after_let_comment"],
        }
        layers.append(layer_dict)
    return layers


def _write_scope_layers(
    expr: NixExpression,
    layers: list[ScopeLayer],
    *,
    restored_layer: ScopeLayer | None = None,
) -> None:
    """Persist edited scope layers back onto the expression (internal CLI helper)."""
    if not layers:
        preserved_before = list(expr.before)
        preserved_after = list(expr.after)
        expr.scope = Scope()
        expr.scope_state = ScopeState()
        if restored_layer is not None:  # pragma: no cover - defensive restoration path
            restored_before = list(restored_layer.get("body_before", ()))
            restored_after = list(restored_layer.get("body_after", ()))
            expr.before = restored_before or preserved_before
            expr.after = restored_after + [
                item for item in preserved_after if item not in restored_after
            ]
        else:
            expr.before = (
                preserved_before  # pragma: no cover - defensive preservation path
            )
            expr.after = (
                preserved_after  # pragma: no cover - defensive preservation path
            )
        return

    outer = layers[0]
    outer_scope = outer["scope"]
    expr.scope = outer_scope if isinstance(outer_scope, Scope) else Scope(outer_scope)
    expr.scope_state = ScopeState(
        body_before=list(outer["body_before"]),
        body_after=list(outer["body_after"]),
        attrpath_order=list(outer["attrpath_order"]),
        after_let_comment=outer["after_let_comment"],
        stack=[
            {
                "scope": layer["scope"],
                "body_before": list(layer["body_before"]),
                "body_after": list(layer["body_after"]),
                "attrpath_order": list(layer["attrpath_order"]),
                "after_let_comment": layer["after_let_comment"],
            }
            for layer in layers[1:]
            if layer.get("scope")
        ],
    )


def set_value(source: NixSourceCode, npath: str, value: str) -> str:
    """Apply a single valid expression value so edits never drop input (CLI helper; not a stable public API)."""
    parsed_value = parse(value)
    if not parsed_value.expressions:
        raise ValueError("Provided value contains no expressions")
    if len(parsed_value.expressions) != 1 or isinstance(
        parsed_value.expressions[0], RawExpression
    ):
        raise ValueError("Provided value must contain exactly one valid expression")
    value_expr = parsed_value.expressions[0]

    if not source.expressions:
        raise ValueError("Source contains no expressions")
    if len(source.expressions) != 1:
        raise ValueError(
            "Top-level expression must be an attribute set or function definition"
        )

    scope_path = _split_scope_npath(npath)
    let_bindings: list[Binding] = []
    if source.expressions:
        top_expr = source.expressions[0]
        if isinstance(top_expr, LetExpression):
            let_bindings = [
                binding
                for binding in top_expr.local_variables
                if isinstance(binding, Binding)
            ]
        elif getattr(top_expr, "scope_state", None) and top_expr.scope:
            let_bindings = [
                binding for binding in top_expr.scope if isinstance(binding, Binding)
            ]
    if scope_path is not None:
        depth, scope_npath = scope_path
        target_expr = _resolve_target_set(source)
        layers = _collect_scope_layers(target_expr)

        if not layers and depth == 1:
            if isinstance(target_expr, AttributeSet):
                segments = _format_npath_segments(scope_npath)
                if _path_exists_in_attrset(target_expr, segments):
                    _set_value_in_attrset(
                        target_expr, scope_npath, value_expr, let_bindings=let_bindings
                    )
                    return source.rebuild()
            # Create an innermost scope and capture existing trivia as the body.
            new_layer: ScopeLayer = {
                "scope": Scope(),
                "body_before": list(target_expr.before),
                "body_after": list(target_expr.after),
                "attrpath_order": [],
                "after_let_comment": None,
            }
            layers.append(new_layer)
            target_expr.before = []
            target_expr.after = []

        if depth > len(layers):
            raise ValueError("Requested scope layer does not exist")

        target_layer = layers[-depth]
        attrset = AttributeSet(
            values=cast(list[Binding | Inherit], target_layer["scope"]),
            attrpath_order=cast(
                list[Binding | Inherit | _AttrpathEntry],
                target_layer["attrpath_order"],
            ),
        )
        _set_value_in_attrset(
            attrset, scope_npath, value_expr, let_bindings=let_bindings
        )
        _write_scope_layers(target_expr, layers)
        return source.rebuild()

    resolution = _resolve_npath(source, npath)
    target_set = resolution.target_set
    _set_value_in_attrset(target_set, npath, value_expr, let_bindings=let_bindings)
    return source.rebuild()


def remove_value(source: NixSourceCode, npath: str) -> str:
    """Delete a value with explicit error signaling for missing keys (CLI helper; not a stable public API)."""
    if not source.expressions:
        raise ValueError("Source contains no expressions")
    if len(source.expressions) != 1:
        raise ValueError(
            "Top-level expression must be an attribute set or function definition"
        )

    scope_path = _split_scope_npath(npath)
    if scope_path is not None:
        depth, scope_npath = scope_path
        target_expr = _resolve_target_set(source)
        layers = _collect_scope_layers(target_expr)
        original_trailing = list(source.trailing)
        if depth > len(layers):
            raise ValueError("Requested scope layer does not exist")

        layer_index = len(layers) - depth
        target_layer = layers[layer_index]
        attrset = AttributeSet(
            values=cast(list[Binding | Inherit], target_layer["scope"]),
            attrpath_order=cast(
                list[Binding | Inherit | _AttrpathEntry],
                target_layer["attrpath_order"],
            ),
        )
        _remove_value_in_attrset(attrset, scope_npath)

        removed_layer: ScopeLayer | None = None
        if not target_layer["scope"]:
            removed_layer = target_layer
            del layers[layer_index]

        _write_scope_layers(target_expr, layers, restored_layer=removed_layer)
        if removed_layer and not layers:
            # Dropping the final layout newline keeps round-tripped files aligned
            # with prior formatting (e.g., trailing comments without an extra EOL).
            while source.trailing and source.trailing[-1] in (linebreak, empty_line):
                source.trailing.pop()
        if removed_layer and removed_layer.get(
            "body_after"
        ):  # pragma: no cover - defensive restoration
            # Restore trailing trivia that was stashed on the scope layer.
            if not source.trailing:
                source.trailing = list(removed_layer["body_after"])
            else:
                existing_ids = {id(item) for item in source.trailing}
                source.trailing.extend(
                    item
                    for item in removed_layer["body_after"]
                    if id(item) not in existing_ids
                )
        if (
            not source.trailing and original_trailing
        ):  # pragma: no cover - defensive restoration
            source.trailing = original_trailing
        rebuilt = source.rebuild()
        if removed_layer and not layers and removed_layer.get("body_before"):
            rebuilt = rebuilt.rstrip("\n")
        return rebuilt

    resolution = _resolve_npath(source, npath)
    target_set = resolution.target_set
    segments = resolution.segments
    if resolution.attrpath_leaf is not None:
        _remove_attrpath_value(target_set, segments)
        return source.rebuild()
    if len(segments) == 1:
        key = segments[0]
        if resolution.attrpath_root is not None:
            raise KeyError(key)
        binding = _find_binding(target_set, key)
        if binding is None:
            raise KeyError(key)
        del target_set[key]
        return source.rebuild()
    if resolution.attrpath_root is not None:
        _remove_attrpath_value(target_set, segments)
        return (
            source.rebuild()
        )  # pragma: no cover - attrpath branch covered in other tests
    parent_set, final_key = _resolve_npath_parent(
        target_set, npath, create_missing=False
    )
    del parent_set[final_key]
    return source.rebuild()
