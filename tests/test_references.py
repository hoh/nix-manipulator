import textwrap

import pytest

from nix_manipulator import parse
from nix_manipulator.exceptions import ResolutionError
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.scope import Scope
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.with_statement import WithStatement
from nix_manipulator.resolution import (attach_resolution_context,
                                        function_call_scope,
                                        get_resolution_context,
                                        scopes_for_owner,
                                        set_resolution_context)


def nix(src: str):
    return parse(textwrap.dedent(src).strip())


def test_reference_lookup_in_let():
    """Identifier access through let bindings should resolve to the defining value."""
    source = nix(
        """
        let
          a = 3;
        in
        {
          foo = a;
        }
        """
    )
    expr = source.expr
    assert expr.scope["a"].value == 3
    assert expr["foo"].value == 3


def test_reference_chain_updates_defining_binding():
    """Chained references update the original binding when assigned through any alias."""
    source = nix(
        """
        let
          a = b;
          b = c;
          c = 3;
        in
        {
          foo = a;
          bar = b;
        }
        """
    )
    expr = source.expr
    assert expr.scope["c"].value == 3
    assert expr["foo"].value == 3
    assert expr["bar"].value == 3

    expr["foo"].value = 10
    assert expr.scope["c"].value == 10
    assert expr["bar"].value == 10

    expr["bar"].value = 11
    assert expr.scope["c"].value == 11
    assert expr["foo"].value == 11


def test_identifier_needs_scope_context():
    """Resolution without an attached scope should fail loudly."""
    ident = nix("missing").expr
    with pytest.raises(ResolutionError):
        _ = ident.value
    with pytest.raises(ResolutionError):
        ident.value = 1


def test_identifier_resolves_and_coerces_values():
    """Resolution should coerce raw Python values into Nix expressions."""
    scope = nix(
        """
        let
          a = 1;
        in
        a
        """
    ).expr.scope
    scope.get_binding("a").value = 1  # raw Python value to trigger coercion
    ident = Identifier("a")
    set_resolution_context(ident, (scope,))

    resolved = ident.value
    assert isinstance(resolved, Primitive)
    assert resolved.value == 1
    assert isinstance(scope.get_binding("a").value, Primitive)


def test_identifier_reports_unbound_names():
    """Unbound identifiers in known scopes must raise ResolutionError."""
    scope = nix(
        """
        let
          a = 1;
        in
        a
        """
    ).expr.scope
    ident = Identifier("other")
    set_resolution_context(ident, (scope,))
    with pytest.raises(ResolutionError):
        _ = ident.value


def test_identifier_cycle_detection():
    """Cyclic reference chains should be detected and rejected."""
    expr = nix(
        """
        let
          a = b;
          b = a;
        in
        a
        """
    ).expr
    cyclic = expr.scope["a"]
    with pytest.raises(ResolutionError):
        _ = cyclic.value


def test_identifier_assignment_preserves_trivia():
    """Assigning through an identifier keeps the original trivia intact."""
    scoped = nix(
        """
        let
          c = 3;
        in
        c
        """
    ).expr.scope
    binding = scoped.get_binding("c")
    binding.value.before = [Comment("keep-before")]
    binding.value.after = [Comment("keep-after")]

    ref = Identifier("c")
    set_resolution_context(ref, (scoped,))
    ref.value = Primitive(5)

    updated = scoped.get_binding("c").value
    assert updated.value == 5
    assert any(isinstance(item, Comment) for item in updated.before)
    assert any(isinstance(item, Comment) for item in updated.after)


def test_attach_context_collects_owner_scope_stack():
    """Context attachment should gather scopes from the owning expression."""
    owner = nix("{ x = 1; }").expr
    owner.scope = Scope(owner.values)
    owner.scope_state.stack = [
        {
            "scope": [Binding(name="y", value=2)],
            "body_before": [],
            "body_after": [],
            "attrpath_order": [],
            "after_let_comment": None,
        }
    ]
    target = Identifier("x")

    attach_resolution_context(target, owner=owner)
    context = get_resolution_context(target)
    assert context is not None
    scope, stacked = context.scopes
    assert scope.get_binding("x").value == 1
    assert stacked.get_binding("y").value == 2


def test_scopes_for_owner_include_inherited_context():
    """Inherited and owner scopes must be ordered correctly in the resolution chain."""
    owner = nix("{ root = 1; }").expr
    owner.scope = Scope(owner.values)
    set_resolution_context(owner, (Scope([Binding(name="inherited", value=2)]),))
    owner.scope_state.stack = [
        {
            "scope": [Binding(name="stacked", value=3)],
            "body_before": [],
            "body_after": [],
            "attrpath_order": [],
            "after_let_comment": None,
        }
    ]

    scopes = scopes_for_owner(owner)
    inherited_scope, root_scope, stacked_scope = scopes
    assert inherited_scope.get_binding("inherited").value == 2
    assert root_scope.get_binding("root").value == 1
    assert stacked_scope.get_binding("stacked").value == 3

    target = Identifier("root")
    attach_resolution_context(target, owner=owner)
    context = get_resolution_context(target)
    assert context is not None
    assert len(context.scopes) == 3


def test_empty_resolution_context_is_ignored():
    """An empty context should not be stored on the identifier."""
    ident = nix("none").expr
    set_resolution_context(ident, ())
    assert get_resolution_context(ident) is None


def test_resolution_skips_non_scope_entries():
    """Non-scope entries in the context must be ignored and still error cleanly."""
    ident = nix("missing").expr
    set_resolution_context(ident, (Scope(), "not-a-scope"))
    with pytest.raises(ResolutionError):
        _ = ident.value


def test_attach_resolution_context_reuses_existing_scope_chain():
    """Reattaching context should preserve a previously set scope chain."""
    scope = nix(
        """
        let
          z = 1;
        in
        z
        """
    ).expr.scope
    inherited = nix("z").expr
    set_resolution_context(inherited, (scope,))
    attach_resolution_context(inherited)
    context = get_resolution_context(inherited)
    assert context is not None
    assert context.scopes == (scope,)


def test_reference_recursive_attrset():
    """Recursive attribute sets resolve sibling references and track updates."""
    source = nix(
        """
        rec {
          foo = bar;
          bar = 42;
        }
        """
    )
    expr = source.expr
    assert expr["foo"].value == 42
    expr["bar"].value = 0
    assert expr["foo"].value == 0


def test_reference_inherit_from_attrset():
    """Inherited attributes should alias their defining bindings."""
    source = nix(
        """
        let
          base = { a = 1; };
        in
        {
          inherit (base) a;
        }
        """
    )
    expr = source.expr
    assert expr["a"].value == 1
    expr.scope["base"]["a"].value = 2
    assert expr["a"].value == 2


def test_reference_inherit_from_expr():
    """Inherited attributes should follow nested sources."""
    source = nix(
        """
        let
          base = { a = 5; };
          wrap = rec { inherit (base) a; };
        in
        wrap
        """
    )
    wrapped = source.expr
    attach_resolution_context(wrapped, owner=wrapped)
    resolved = wrapped.value
    assert resolved["a"].value == 5
    wrapped.scope["base"]["a"].value = 9
    assert resolved["a"].value == 9


def test_reference_with_scope():
    """With environments should expose their bindings to the body."""
    source = nix(
        """
        with { a = 5; };
        {
          foo = a;
        }
        """
    )
    expr = source.expr
    assert expr["foo"].value == 5
    expr.environment["a"].value = 8
    assert expr["foo"].value == 8


def test_reference_with_scope_rejects_non_attr_environment():
    """With environments that are not attrsets should raise ResolutionError."""
    expr = nix(
        """
        let
          env = 1;
        in
        with env;
        { foo = a; }
        """
    ).expr
    with pytest.raises(ResolutionError, match="environment must resolve to an attribute set"):
        _ = expr["foo"].value


def test_reference_with_scope_rejects_literal_environment():
    """With environments that are not resolvable expressions should raise ResolutionError."""
    expr = nix(
        """
        with 1;
        { foo = a; }
        """
    ).expr
    with pytest.raises(ResolutionError, match="environment must resolve to an attribute set"):
        _ = expr["foo"].value


def test_reference_function_parameters():
    """Function arguments and defaults should form a resolution scope."""
    source = nix(
        """
        ({ a, b ? 2 }:
          b
        ) { a = 1; }
        """
    )
    call = source.expr
    param_scope = function_call_scope(call)
    assert param_scope is not None
    assert param_scope.get_binding("a").value == 1
    assert param_scope.get_binding("b").value == 2

    function = call.name
    if isinstance(function, Parenthesis):
        function = function.value
    assert isinstance(function, FunctionDefinition)

    result = function.output
    if result is not None:
        set_resolution_context(result, (param_scope,))
        attach_resolution_context(result, owner=result)
        assert result.value == 2

        param_scope.get_binding("b").value = 10
        assert result.value == 10


def test_function_call_scope_rejects_non_call_inputs():
    """Non-call inputs should be ignored when building parameter scopes."""
    assert function_call_scope(Identifier("x")) is None


def test_function_call_scope_skips_non_function_targets():
    """Calls that target non-functions should not create parameter scopes."""
    call = nix("x { a = 1; }").expr
    assert function_call_scope(call) is None


def test_function_call_scope_requires_attrset_argument():
    """Function call scope construction should reject non-attrset arguments."""
    call = nix("({ x }: x) 1").expr
    with pytest.raises(ResolutionError):
        function_call_scope(call)

def test_function_call_scope_accepts_identifier_argument():
    """Identifiers resolving to attrsets should be accepted as call arguments."""
    call = nix(
        """
        let
          args = { x = 1; };
        in
        ({ x }: x) args
        """
    ).expr
    scope = function_call_scope(call)
    assert scope is not None
    assert scope.get_binding("x").value == 1


def test_function_call_scope_accepts_parenthesized_attrset_argument():
    """Parenthesized attrset arguments should also build parameter scopes."""
    call = nix("({ x }: x) ({ x = 2; })").expr
    scope = function_call_scope(call)
    assert scope is not None
    assert scope.get_binding("x").value == 2


def test_function_call_scope_uses_scope_stack_for_identifier_argument():
    """Scope stacks on the call should provide context for identifier arguments."""
    binding = Binding(name="args", value=AttributeSet({"x": 1}))
    function = FunctionDefinition(argument_set=[Identifier("x")], output=Identifier("x"))
    call = FunctionCall(name=function, argument=Identifier("args"))
    call.scope_state.stack = [
        {
            "scope": [binding],
            "body_before": [],
            "body_after": [],
            "attrpath_order": [],
            "after_let_comment": None,
        }
    ]

    scope = function_call_scope(call)
    assert scope is not None
    assert scope.get_binding("x").value == 1


def test_function_call_scope_positional_identifier_argument_resolves():
    """Identifier arguments to positional params should use available scopes."""
    call = nix(
        """
        let
          arg = 5;
        in
        (x: x) arg
        """
    ).expr
    param_scope = function_call_scope(call)
    assert param_scope is not None
    assert param_scope.get_binding("x").value == 5


def test_function_call_scope_none_argument_errors():
    """Missing arguments should raise when resolving attrset parameters."""
    function = FunctionDefinition(argument_set=[Identifier("x")], output=Primitive(1))
    call = FunctionCall(name=function, argument=None)
    with pytest.raises(ResolutionError):
        function_call_scope(call)


def test_function_call_scope_accepts_identifier_parameters():
    """Positional function arguments should build scopes without requiring attrsets."""
    call = nix("(x: x) 5").expr
    param_scope = function_call_scope(call)
    assert param_scope is not None
    assert param_scope.get_binding("x").value == 5


def test_function_call_scope_skips_non_identifier_parameters():
    """Non-identifier params (like ellipses) should be ignored cleanly."""
    function = FunctionDefinition(argument_set=[Ellipses()], output=Primitive(1))
    call = FunctionCall(name=function, argument=AttributeSet(values=[]))
    scope = function_call_scope(call)
    assert scope is not None
    assert len(scope) == 0


def test_function_call_scope_missing_identifier_argument_errors():
    """Identifier parameters require a provided argument."""
    function = FunctionDefinition(argument_set=Identifier("x"), output=Primitive(1))
    call = FunctionCall(name=function, argument=None)
    with pytest.raises(ResolutionError):
        function_call_scope(call)


def test_function_call_scope_unsupported_parameter_type():
    """Unsupported parameter structures should be ignored."""
    function = FunctionDefinition(argument_set="bogus", output=Primitive(1))  # type: ignore[arg-type]
    call = FunctionCall(name=function, argument=Primitive(1))
    assert function_call_scope(call) is None


def test_function_call_scope_requires_all_arguments():
    """Missing required function parameters should raise during resolution."""
    call = nix("({ x }: x) {}").expr
    with pytest.raises(ResolutionError):
        function_call_scope(call)


def test_with_statement_resolves_identifier_environment():
    """With statements should resolve identifier environments before use."""
    expr = nix(
        """
        let
          env = { a = 7; };
        in
        with env; { foo = a; }
        """
    ).expr
    assert expr["foo"].value == 7


def test_with_statement_accepts_scope_environment():
    """Scopes can be used directly as with environments in procedural construction."""
    env_scope = Scope([Binding(name="a", value=3)])
    stmt = WithStatement(environment=env_scope, body=Identifier("a"))
    attach_resolution_context(stmt.body, owner=stmt)
    assert stmt.body.value == 3


def test_function_call_scopes_for_owner():
    """Function call owners should expose parameter scopes via scopes_for_owner."""
    call = nix("({ x }: x) { x = 7; }").expr
    scopes = scopes_for_owner(call)
    assert any(
        isinstance(scope, Scope)
        and scope._find_binding_index("x") is not None
        and scope.get_binding("x").value == 7
        for scope in scopes
    )


def test_scopes_for_owner_propagates_function_call_scope_errors():
    """Scope collection should surface function call resolution errors."""
    call = nix("({ x }: x) 1").expr
    with pytest.raises(ResolutionError, match="attribute set argument"):
        scopes_for_owner(call)


def test_inherit_with_quoted_names_resolves():
    """Quoted inherit names should resolve exactly like identifier-based inherits."""
    expr = nix(
        """
        let
          base = { "foo" = 1; };
        in
        {
          inherit (base) "foo";
        }
        """
    ).expr
    assert expr["foo"].value == 1


def test_identifier_resolution_context_is_cleared_when_reparented():
    """Moving an identifier into a new scope should drop any inherited context."""
    original_scope = Scope([Binding(name="a", value=1)])
    ident = Identifier("a")
    set_resolution_context(ident, (original_scope,))

    new_scope = Scope()
    new_scope["a"] = ident

    with pytest.raises(ResolutionError):
        _ = ident.value


def test_resolution_contexts_do_not_leak():
    """Stored contexts should be released with their owners."""
    import gc

    import nix_manipulator.resolution as res

    scope = Scope([Binding(name="a", value=1)])
    ident = Identifier("a")
    set_resolution_context(ident, (scope,))
    assert get_resolution_context(ident) is not None

    context_id = next(
        key for key, (ref_obj, _) in res._CONTEXTS.items() if ref_obj() is ident
    )

    del ident
    gc.collect()

    assert context_id not in res._CONTEXTS


def test_resolution_context_callback_tolerates_missing_entry():
    """GC callbacks should no-op if the context entry was removed early."""
    import gc

    import nix_manipulator.resolution as res

    expr = Identifier("x")
    expr_id = id(expr)
    set_resolution_context(expr, (Scope(),))
    entry = res._CONTEXTS.pop(expr_id, None)
    assert entry is not None
    del expr
    gc.collect()
    # No errors from callback and the manual removal sticks.
    assert expr_id not in res._CONTEXTS


def test_resolution_context_stale_entry_is_pruned():
    """Stale id lookups should drop mismatched context entries."""
    import nix_manipulator.resolution as res

    res._CONTEXTS.clear()
    owner = Identifier("owner")
    set_resolution_context(owner, (Scope(),))

    bogus = Identifier("bogus")
    res._CONTEXTS[id(bogus)] = res._CONTEXTS[id(owner)]
    assert get_resolution_context(bogus) is None
    assert id(bogus) not in res._CONTEXTS


def test_attrset_assignment_clears_identifier_context():
    """Assigning identifiers into new attrsets should clear stale contexts."""
    original = nix(
        """
        {
          a = 1;
        }
        """
    ).expr
    ident = Identifier("a")
    set_resolution_context(ident, (original.scope,))

    target = nix("{ }").expr
    target["a"] = ident

    with pytest.raises(ResolutionError):
        _ = target["a"].value


def test_identifier_moved_between_attrsets_needs_reattachment():
    """Moving identifiers across attrsets should require attaching the new scope."""
    expr = nix(
        """
        {
          left = { val = 1; ref = val; };
          right = { val = 2; };
        }
        """
    ).expr

    left = expr["left"]
    right = expr["right"]

    moved = left["ref"]
    right["ref"] = moved

    with pytest.raises(ResolutionError):
        _ = moved.value

    reparent_scope = Scope(right.values)
    set_resolution_context(moved, (reparent_scope,))
    assert moved.value == 2

    rebuilt = expr.rebuild()
    assert (
        rebuilt
        == textwrap.dedent(
            """
            {
              left = { val = 1; ref = val; };
              right = { val = 2; ref = val; };
            }
            """
        ).strip()
    )


def test_inherit_without_source_is_unbound():
    """Inherit with no source should raise when the name is not otherwise bound."""
    expr = nix(
        """
        {
          inherit missing;
        }
        """
    ).expr
    with pytest.raises(ResolutionError):
        _ = expr["missing"].value


def test_inherit_supports_scope_sources():
    """Scopes used as inherit sources should be accepted for resolution."""
    source_scope = Scope([Binding(name="foo", value=Primitive(5))])
    inherit_entry = Inherit(names=[Identifier("foo")], from_expression=source_scope)
    scope = Scope([inherit_entry])
    identifier = Identifier("foo")
    set_resolution_context(identifier, (scope,))
    assert identifier.value.value == 5


def test_inherit_rejects_non_attr_sources():
    """Inherit sources that do not expose attributes should raise ResolutionError."""
    inherit_entry = Inherit(names=[Identifier("foo")], from_expression=Primitive(1))
    scope = Scope([inherit_entry])
    identifier = Identifier("foo")
    set_resolution_context(identifier, (scope,))
    with pytest.raises(ResolutionError):
        _ = identifier.value
