"""Fill coverage gaps in manipulation helpers."""

from textwrap import dedent
from types import SimpleNamespace

import pytest

import nix_manipulator.cli.manipulations as manipulations_module
from nix_manipulator import parser
from nix_manipulator.cli.manipulations import (
    _remove_value_in_attrset,
    _resolve_inherited_binding,
    _resolve_npath_parent,
    _resolve_target_set,
    _resolve_target_set_from_expr,
    _set_attrpath_value,
    _set_value_in_attrset,
    _walk_attrpath_stack,
    remove_value,
    set_value,
)
from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.scope import Scope
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.source_code import NixSourceCode


def test_resolve_target_set_from_expr_errors():
    """Exercise error branches for unexpected expression types."""
    with pytest.raises(ValueError, match="Unexpected assertion without body"):
        _resolve_target_set_from_expr(Assertion(expression=Primitive(value=True)))

    bad_output = FunctionDefinition(
        argument_set=Identifier(name="x"),
        output=Primitive(value=1),
    )
    with pytest.raises(ValueError, match="Unexpected function output type"):
        _resolve_target_set_from_expr(bad_output)

    with pytest.raises(ValueError, match="Unexpected expression type"):
        _resolve_target_set_from_expr(Primitive(value=1))


def test_resolve_target_set_function_call_output():
    """Resolve function outputs that wrap attribute sets."""
    output = FunctionCall(
        name=Identifier(name="f"),
        argument=AttributeSet(values=[]),
    )
    fn = FunctionDefinition(argument_set=Identifier(name="x"), output=output)
    assert isinstance(_resolve_target_set_from_expr(fn), AttributeSet)


def test_resolve_target_set_rejects_multiple_expressions():
    """Reject multi-expression sources for deterministic edits."""
    source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[Primitive(value=1), Primitive(value=2)],
    )
    with pytest.raises(
        ValueError, match="Source must contain exactly one top-level expression"
    ):
        _resolve_target_set(source)


def test_resolve_target_set_variants():
    """Follow wrappers like let/parenthesis and parenthesized callees."""
    attrset = AttributeSet.from_dict({"a": Primitive(value=1)})
    let_expr = LetExpression(local_variables=[], value=attrset)
    assert _resolve_target_set_from_expr(let_expr) is attrset

    paren = Parenthesis(value=attrset)
    assert _resolve_target_set_from_expr(paren) is attrset

    call = FunctionCall(
        name=Parenthesis(value=Identifier(name="f")),
        argument=AttributeSet(values=[]),
    )
    assert _resolve_target_set_from_expr(call) is call.argument


def test_resolve_target_set_function_call_nested_and_string_callee():
    """Nested call callees and string names should still resolve attrset arguments."""
    # nixpkgs-style call sites can use higher-order wrappers: (f 1) { ... }.
    # We still need to target the attrset argument for `nima set`.
    nested_source = parser.parse("(f 1) { }")
    nested = nested_source.expressions[0]
    assert isinstance(nested, FunctionCall)
    assert _resolve_target_set_from_expr(nested) is nested.argument

    # Some parser/manipulation paths can expose the callee as a raw string.
    # Treating it like an identifier keeps edits resilient to representation drift.
    call_source = parser.parse("f { }")
    call = call_source.expressions[0]
    assert isinstance(call, FunctionCall)
    call.name = "f"
    assert _resolve_target_set_from_expr(call) is call.argument


def test_resolve_target_set_function_call_identifier_argument_resolution():
    """Function-call identifier arguments should unwrap and resolve through scopes."""
    # Real package files often pass a named binding, e.g. `f (body)`,
    # and `body` contains the attrset that `nima set` must update.
    resolved_scope_source = parser.parse("{ body = { }; }")
    resolved_target = resolved_scope_source.expressions[0]
    assert isinstance(resolved_target, AttributeSet)
    resolved_scope = Scope(resolved_target.values)
    resolved_binding = next(
        binding
        for binding in resolved_target.values
        if isinstance(binding, Binding) and binding.name == "body"
    )
    assert isinstance(resolved_binding.value, AttributeSet)

    call_source = parser.parse("f (body)")
    call = call_source.expressions[0]
    assert isinstance(call, FunctionCall)
    assert (
        _resolve_target_set_from_expr(call, scope_chain=(resolved_scope,))
        is resolved_binding.value
    )

    # If the identifier resolves to a non-attrset, the edit target is ambiguous.
    # Failing fast here avoids silently mutating the wrong expression.
    unresolved_scope_source = parser.parse("{ body = 1; }")
    unresolved_target = unresolved_scope_source.expressions[0]
    assert isinstance(unresolved_target, AttributeSet)
    unresolved_scope = Scope(unresolved_target.values)
    failing_source = parser.parse("f (body)")
    failing = failing_source.expressions[0]
    assert isinstance(failing, FunctionCall)
    with pytest.raises(ValueError, match="Unexpected expression type"):
        _resolve_target_set_from_expr(failing, scope_chain=(unresolved_scope,))


def test_resolve_target_set_cycle_detection_and_empty_output():
    """Raise on unexpected recursion and missing function outputs."""
    assertion = Assertion(expression=Primitive(value=True), body=None)
    assertion.body = assertion
    with pytest.raises(ValueError, match="Unexpected expression type"):
        _resolve_target_set_from_expr(assertion)

    empty_output = FunctionDefinition(argument_set=Identifier(name="x"), output=None)
    with pytest.raises(ValueError, match="Unexpected function output type"):
        _resolve_target_set_from_expr(empty_output)


def test_resolve_target_set_rejects_empty_and_invalid_top_level():
    """Validate empty sources and disallowed top-level expressions."""
    empty = NixSourceCode(node=SimpleNamespace(), expressions=[])
    with pytest.raises(ValueError, match="Source contains no expressions"):
        _resolve_target_set(empty)

    invalid = NixSourceCode(node=SimpleNamespace(), expressions=[Primitive(value=1)])
    with pytest.raises(
        ValueError,
        match="Top-level expression must be an attribute set or function definition",
    ):
        _resolve_target_set(invalid)


def test_walk_attrpath_stack_errors_and_type_checks():
    """Ensure attrpath traversal reports missing and invalid segments."""
    target = AttributeSet(values=[], multiline=False)
    with pytest.raises(KeyError):
        _walk_attrpath_stack(target, ["root"], leaf_nested=False, require_root=True)
    with pytest.raises(KeyError):
        _walk_attrpath_stack(
            target, ["root", "leaf"], leaf_nested=False, require_root=True
        )

    child_binding = Binding(name="child", value=Primitive(value=1), nested=True)
    root = Binding(
        name="root",
        value=AttributeSet(values=[child_binding], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[root], multiline=False)
    with pytest.raises(
        ValueError, match="NPath segment does not point to an attribute set: child"
    ):
        _walk_attrpath_stack(
            target, ["root", "child", "leaf"], leaf_nested=False, require_root=True
        )


def test_set_attrpath_value_error_and_update_paths():
    """Guard against mixed bindings and allow overwriting leaf bindings."""
    explicit_child = Binding(name="child", value=Primitive(value=0), nested=False)
    explicit_root = Binding(
        name="root",
        value=AttributeSet(values=[explicit_child], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[explicit_root], multiline=False)
    with pytest.raises(
        ValueError, match="Mixed explicit binding inside attrpath: child"
    ):
        _set_attrpath_value(
            target, explicit_root, ["root", "child", "leaf"], Primitive(value=1)
        )

    wrong_type_child = Binding(name="child", value=Primitive(value=0), nested=True)
    wrong_type_root = Binding(
        name="root",
        value=AttributeSet(values=[wrong_type_child], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[wrong_type_root], multiline=False)
    with pytest.raises(
        ValueError, match="NPath segment does not point to an attribute set: child"
    ):
        _set_attrpath_value(
            target, wrong_type_root, ["root", "child", "leaf"], Primitive(value=1)
        )

    leaf_binding = Binding(name="leaf", value=Primitive(value=0))
    nested_child = Binding(
        name="child",
        value=AttributeSet(values=[leaf_binding], multiline=False),
        nested=True,
    )
    update_root = Binding(
        name="root",
        value=AttributeSet(values=[nested_child], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[update_root], multiline=False)
    _set_attrpath_value(
        target, update_root, ["root", "child", "leaf"], Primitive(value=2)
    )
    assert isinstance(leaf_binding.value, Primitive)
    assert leaf_binding.value.value == 2


def test_resolve_npath_parent_errors_on_missing_segments():
    """Bubble up missing-segment and type errors from parent resolution."""
    target = AttributeSet(values=[], multiline=False)
    with pytest.raises(KeyError, match="NPath segment not found: foo"):
        _resolve_npath_parent(target, "foo.bar", create_missing=False)

    target = AttributeSet.from_dict({"foo": Primitive(value=1)})
    with pytest.raises(
        ValueError, match="NPath segment does not point to an attribute set: foo"
    ):
        _resolve_npath_parent(target, "foo.bar", create_missing=True)


def test_resolve_inherited_binding_prefers_local_then_outer():
    """Follow inherits inside function-call arguments to a concrete binding."""
    inherit_block = AttributeSet(
        values=[Inherit(names=[Identifier(name="version")])],
        multiline=False,
    )
    local_version = Binding(name="version", value=Primitive(value="1.0"))
    target_set = AttributeSet(
        values=[
            local_version,
            Binding(
                name="src",
                value=FunctionCall(
                    name=Identifier(name="fetch"),
                    argument=inherit_block,
                ),
            ),
        ]
    )
    assert (
        _resolve_inherited_binding(target_set, root_key="src", leaf_key="version")
        is local_version
    )

    outer_binding = Binding(name="version", value=Primitive(value="2.0"))
    target_set = AttributeSet(
        values=[
            Binding(
                name="src",
                value=FunctionCall(
                    name=Identifier(name="fetch"),
                    argument=inherit_block,
                ),
            ),
        ]
    )
    assert (
        _resolve_inherited_binding(
            target_set,
            root_key="src",
            leaf_key="version",
            outer_bindings=[outer_binding],
        )
        is outer_binding
    )


def test_set_value_in_attrset_updates_let_binding():
    """Write through identifiers to outer let bindings instead of overwriting."""
    target_set = AttributeSet(
        values=[Binding(name="pkgVersion", value=Identifier(name="ref"))],
        multiline=False,
    )
    let_binding = Binding(name="ref", value=Primitive(value="1.0"))
    new_value = Primitive(value="2.0")
    _set_value_in_attrset(
        target_set, "pkgVersion", new_value, let_bindings=[let_binding]
    )
    assert let_binding.value is new_value
    assert isinstance(target_set.values[0].value, Identifier)


def test_set_value_in_attrset_updates_inherited_identifier():
    """Handle inherited identifiers inside function-call arguments."""
    let_binding = Binding(name="package_version", value=Primitive(value="2025.9.4"))
    inherit_block = AttributeSet(
        values=[Inherit(names=[Identifier(name="version")])],
        multiline=False,
    )
    version_binding = Binding(name="version", value=Identifier(name="package_version"))
    target_set = AttributeSet(
        values=[
            version_binding,
            Binding(
                name="src",
                value=FunctionCall(
                    name=Identifier(name="fetchPypi"),
                    argument=inherit_block,
                ),
            ),
        ]
    )
    updated = Primitive(value="2026.1.2")
    _set_value_in_attrset(
        target_set,
        "src.version",
        updated,
        let_bindings=[let_binding],
    )
    assert let_binding.value is updated
    assert isinstance(version_binding.value, Identifier)


def test_remove_value_in_attrset_attrpath_errors():
    """Surface attrpath-root and missing-key errors for removals."""
    nested = AttributeSet(
        values=[Binding(name="leaf", value=Primitive(value=1))], multiline=False
    )
    attrpath_root = Binding(name="root", value=nested, nested=True)
    attrpath_target = AttributeSet(values=[attrpath_root], multiline=False)
    with pytest.raises(KeyError):
        _remove_value_in_attrset(attrpath_target, "root")

    with pytest.raises(KeyError):
        _remove_value_in_attrset(AttributeSet(values=[], multiline=False), "missing")

    populated_nested = AttributeSet(
        values=[Binding(name="leaf", value=Primitive(value=1))], multiline=False
    )
    removable_root = Binding(name="root", value=populated_nested, nested=True)
    removable = AttributeSet(values=[removable_root], multiline=False)
    _remove_value_in_attrset(removable, "root.leaf")
    assert removable_root.value.values == []


def test_set_value_guards_and_let_binding_handling():
    """Validate top-level guards and let-binding passthrough."""
    empty_source = NixSourceCode(node=SimpleNamespace(), expressions=[])
    with pytest.raises(ValueError, match="Source contains no expressions"):
        set_value(empty_source, "foo", "1")

    multi_source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[Primitive(value=1), Primitive(value=2)],
    )
    with pytest.raises(
        ValueError,
        match="Top-level expression must be an attribute set or function definition",
    ):
        set_value(multi_source, "foo", "1")

    source = parser.parse(
        dedent(
            """
            let
              package_version = "1.0";
            in
            {
              version = package_version;
            }
            """
        )
    )
    updated = set_value(source, "version", '"2.0"')
    updated_source = parser.parse(updated)
    target_expr = updated_source.expressions[0]
    if isinstance(target_expr, LetExpression):
        bindings = target_expr.local_variables
    else:
        assert isinstance(target_expr, AttributeSet)
        bindings = target_expr.scope
    let_binding = next(binding for binding in bindings if isinstance(binding, Binding))
    assert isinstance(let_binding.value, Primitive)
    assert let_binding.value.value == "2.0"


def test_remove_value_top_level_guards():
    """Remove-value should reject empty or multi-expression sources."""
    empty_source = NixSourceCode(node=SimpleNamespace(), expressions=[])
    with pytest.raises(ValueError, match="Source contains no expressions"):
        remove_value(empty_source, "foo")

    multi_source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[Primitive(value=1), Primitive(value=2)],
    )
    with pytest.raises(
        ValueError,
        match="Top-level expression must be an attribute set or function definition",
    ):
        remove_value(multi_source, "foo")


def test_resolve_npath_empty_segments_guard(monkeypatch):
    """_resolve_npath should reject empty segments even after formatting."""
    source = NixSourceCode(
        node=SimpleNamespace(), expressions=[AttributeSet(values=[])]
    )
    monkeypatch.setattr(manipulations_module, "_format_npath_segments", lambda _: [])
    with pytest.raises(ValueError, match="NPath cannot be empty"):
        manipulations_module._resolve_npath(source, "ignored")


def test_walk_attrpath_stack_returns_none_when_non_attrset_without_root():
    """Gracefully return None when traversal hits a non-attrset without require_root."""
    child_binding = Binding(name="child", value=Primitive(value=1), nested=True)
    root = Binding(
        name="root",
        value=AttributeSet(values=[child_binding], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[root], multiline=False)
    assert (
        _walk_attrpath_stack(
            target, ["root", "child", "leaf"], leaf_nested=False, require_root=False
        )
        is None
    )


def test_set_attrpath_value_creates_missing_nested_bindings():
    """Missing nested segments should be created automatically."""
    root = Binding(
        name="root",
        value=AttributeSet(values=[], multiline=False),
        nested=True,
    )
    target = AttributeSet(values=[root], multiline=False)
    value_expr = Primitive(value=1)
    _set_attrpath_value(target, root, ["root", "child", "leaf"], value_expr)
    child_binding = next(
        binding
        for binding in root.value.values
        if isinstance(binding, Binding) and binding.name == "child"
    )
    assert child_binding.nested
    leaf_binding = next(
        binding
        for binding in child_binding.value.values
        if isinstance(binding, Binding) and binding.name == "leaf"
    )
    assert leaf_binding.value is value_expr


def test_resolve_inherited_binding_handles_quoted_names():
    """Inherit entries with literal names should still resolve."""
    inherit_block = AttributeSet(
        values=[Inherit(names=[Primitive(value="quoted-name")])],
        multiline=False,
    )
    version_binding = Binding(name="quoted-name", value=Primitive(value="old"))
    target_set = AttributeSet(
        values=[
            version_binding,
            Binding(
                name="src",
                value=FunctionCall(
                    name=Identifier(name="fetch"),
                    argument=inherit_block,
                ),
            ),
        ]
    )
    assert (
        _resolve_inherited_binding(target_set, root_key="src", leaf_key="quoted-name")
        is version_binding
    )


def test_set_value_in_attrset_inherited_binding_without_identifier():
    """Fallback should write directly when inherited binding is not an identifier."""
    inherit_block = AttributeSet(
        values=[Inherit(names=[Primitive(value="version-with-dash")])],
        multiline=False,
    )
    version_binding = Binding(name="version-with-dash", value=Primitive(value="1.0"))
    target_set = AttributeSet(
        values=[
            version_binding,
            Binding(
                name="src",
                value=FunctionCall(
                    name=Identifier(name="fetch"),
                    argument=inherit_block,
                ),
            ),
        ]
    )
    updated = Primitive(value="2.0")
    _set_value_in_attrset(target_set, 'src."version-with-dash"', updated)
    assert version_binding.value is updated


def test_set_value_in_attrset_updates_identifier_sibling_binding():
    """Identifier values should forward writes to sibling bindings."""
    inner = AttributeSet(
        values=[
            Binding(name="target", value=Identifier(name="other")),
            Binding(name="other", value=Primitive(value=0)),
        ],
        multiline=False,
    )
    target_set = AttributeSet(
        values=[Binding(name="root", value=inner)], multiline=False
    )
    new_value = Primitive(value=5)
    _set_value_in_attrset(target_set, "root.target", new_value)
    sibling = next(
        binding
        for binding in inner.values
        if isinstance(binding, Binding) and binding.name == "other"
    )
    assert sibling.value is new_value


def test_set_value_in_attrset_handles_identifier_assignment_errors(monkeypatch):
    """Identifier resolution failures should fall back to overwriting."""
    target_set = AttributeSet(
        values=[Binding(name="key", value=Identifier(name="missing"))],
        multiline=False,
    )
    monkeypatch.setattr(
        manipulations_module,
        "scopes_for_owner",
        lambda _: (Scope([]),),
    )
    replacement = Primitive(value=1)
    _set_value_in_attrset(target_set, "key", replacement)
    assert target_set["key"] is replacement


def test_set_value_let_expression_branch():
    """Let expressions should expose their bindings for set_value."""
    let_binding = Binding(name="x", value=Primitive(value=1))
    body = AttributeSet(values=[Binding(name="value", value=Identifier(name="x"))])
    source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[LetExpression(local_variables=[let_binding], value=body)],
    )
    set_value(source, "value", "2")
    assert isinstance(let_binding.value, Primitive)
    assert getattr(let_binding.value, "value", None) == 2


def test_set_and_remove_value_empty_npath_guard(monkeypatch):
    """Empty NPaths should trigger explicit errors in helper paths."""
    monkeypatch.setattr(manipulations_module, "_format_npath_segments", lambda _: [])
    target_set = AttributeSet(values=[], multiline=False)
    with pytest.raises(ValueError, match="NPath cannot be empty"):
        _set_value_in_attrset(target_set, "ignored", Primitive(value=1))
    with pytest.raises(ValueError, match="NPath cannot be empty"):
        _remove_value_in_attrset(target_set, "ignored")


def test_remove_value_handles_missing_attrpath_branch():
    """Attrpath removals should surface missing leaves."""
    nested = AttributeSet(values=[], multiline=False)
    root = Binding(name="root", value=nested, nested=True)
    source = NixSourceCode(
        node=SimpleNamespace(),
        expressions=[AttributeSet(values=[root], multiline=False)],
    )
    with pytest.raises(KeyError):
        remove_value(source, "root.missing")
