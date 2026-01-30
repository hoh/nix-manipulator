# Editing and Generating Nix code

Most workflows start by parsing existing Nix, making structured edits, and rebuilding. You can also build expressions from scratch; both paths use the same expression classes.

## Start from existing Nix

```python
from nix_manipulator import parse

src = parse('{ foo = 1; bar = [ 1 "two" ]; }')
target = src.expr                # top-level AttributeSet
target["foo"] = 2                # update a binding
target["bar"].value.append(3)    # extend a list
first = target["bar"][0]         # list access
print(first.value)               # 1
print(src.rebuild())
# {
#   foo = 2;
#   bar = [ 1 "two" 3 ];
# }
```

Attrpaths and nested sets work the same way:

```python
src = parse("{ foo = { bar = 1; }; }")
src["foo"]["bar"] = 2
print(src.rebuild())
# { foo = { bar = 2; }; }
```

When you need to add bindings, assign into the mapping:

```python
src = parse("{ }")
src["name"] = "demo"
print(src.rebuild())
# { name = "demo"; }
```

Tip: a Python `str` becomes a Nix **string literal**. Use `Identifier(name="foo")` when you need to reference a variable or attribute name.

## Value building blocks

- Literals: `Primitive("text")`, `Primitive(True)`, `Primitive(42)`, or let containers coerce these automatically.
- Identifiers: `Identifier("pkg")` for variable/attribute references (do not use `Primitive` if you need a bare name).
- Paths: `NixPath("/nix/store/…")` for path literals. When parsing from disk, paths resolve relative to the source file; otherwise relative paths resolve against the current working directory. `NixPath.value` returns bytes, and `NixPath.text` reads UTF-8.
- Lists: `NixList([...])` with elements that can be expressions or primitives (`None` becomes `null`). `NixList` supports list-style indexing/slicing for convenience.

```python
from nix_manipulator.expressions import Identifier, NixPath, Primitive
from nix_manipulator.expressions.list import NixList

print(Primitive("hi").rebuild())             # "hi"
print(Identifier("version").rebuild())       # version
print(NixPath("./flake.nix").rebuild())      # ./flake.nix
print(NixList([1, True, None]).rebuild())    # [ 1 true null ]
```

- List layout: small/simple lists stay inline; longer ones expand automatically. Override with `multiline=True/False`.

```python
from nix_manipulator.expressions import Identifier
from nix_manipulator.expressions.list import NixList

print(NixList([Identifier("a"), Identifier("b")]).rebuild())
# [ a b ]

print(NixList([Identifier("a"), Identifier("b"), Identifier("c"), Identifier("d"), Identifier("e")]).rebuild())
# [
#   a
#   b
#   c
#   d
#   e
# ]

print(NixList([1, 2], multiline=True).rebuild())   # forces multiline
print(NixList([1, 2], multiline=False).rebuild())  # forces inline
```

## Attribute sets and bindings

Attribute sets are the most common root for generated code.

```python
from nix_manipulator.expressions import AttributeSet, Binding, Inherit

pkg = AttributeSet(
    values=[
        Binding(name="pname", value="demo"),
        Binding(name="version", value="1.2.3"),
        Binding(name="src", value=Identifier("fetchurl")),
        Inherit(names=[Identifier("system")]),
    ]
)
print(pkg.rebuild())
# {
#   pname = "demo";
#   version = "1.2.3";
#   src = fetchurl;
#   inherit system;
# }
```

- Quick dicts: `AttributeSet.from_dict({"pname": "demo", "doCheck": False})`.
- Recursive sets: set `recursive=True` on `AttributeSet` to emit `rec { … }`.
- Attrpaths: set `nested=True` on intermediate bindings to render `foo.bar = 1;`.
- Explicit vs attrpath nesting: `nested=True` keeps an attrpath form, while explicit nested sets render braces. Examples:

  ```python
  from nix_manipulator.expressions import AttributeSet, Binding

  # Attrpath binding
  print(AttributeSet(values=[Binding(
      name="foo",
      nested=True,
      value=AttributeSet(values=[Binding(name="bar", value=1)]),
  )]).rebuild())
  # { foo.bar = 1; }

  # Attrpath with explicit nested segment stops flattening
  explicit = Binding(
      name="foo",
      nested=True,
      value=AttributeSet(values=[Binding(
          name="bar",
          nested=False,  # explicit nested set
          value=AttributeSet(values=[Binding(name="baz", value=1)]),
      )]),
  )
  print(AttributeSet(values=[explicit]).rebuild())
  # {
  #   foo.bar = {
  #     baz = 1;
  #   };
  # }
  ```

- Binding comments and semicolons: inline comments on values stay on the value line and push the semicolon to the next line for RFC-style formatting.

  ```python
  from nix_manipulator.expressions import Binding, Identifier, Comment

  print(Binding(
      name="foo",
      value=Identifier("bar", after=[Comment("note", inline=True)]),
  ).rebuild())
  # foo = bar # note
  # ;
  ```

```python
attrpath = AttributeSet(
    values=[
        Binding(
            name="foo",
            nested=True,
            value=AttributeSet(values=[Binding(name="bar", value=1)]),
        )
    ]
)
print(attrpath.rebuild())
# { foo.bar = 1; }
```

`Binding` accepts Python primitives and dicts (dicts are converted to nested attribute sets). Inherit statements support optional sources via `from_expression`:

```python
from nix_manipulator.expressions import Inherit

inherit_from = Inherit(names=[Identifier("stdenv"), Identifier("lib")], from_expression=Identifier("pkgs"))
```

## Scopes (`let … in`)

- For attribute sets, edit the innermost scope via the `.scope` mapping; it is created on assignment and pruned when emptied.
- For arbitrary expressions, use `LetExpression(local_variables=[...], value=...)`.

```python
from nix_manipulator.expressions import AttributeSet, Binding, LetExpression

pkg = AttributeSet({"pname": "demo"})
pkg.scope["src"] = Identifier("fetchurl")
print(pkg.rebuild())
# let
#   src = fetchurl;
# in
# { pname = "demo"; }

wrapped = LetExpression(
    local_variables=[Binding(name="x", value=1)],
    value=Identifier("x"),
)
print(wrapped.rebuild())
# let
#   x = 1;
# in
# x
```

## References (`Identifier.value`)

- Access an identifier through a scoped expression (e.g., `expr["foo"]` or `expr.scope["bar"]`) to attach resolution context; `.value` then resolves to the defining binding across `let`, attribute sets (including `rec` and `inherit`), `with` environments, and function calls that take attribute-set arguments.
- Resolution follows identifier chains and raises `ResolutionError` on unbound names or cycles.
- Assigning through `.value` updates the defining binding; Python primitives are coerced and existing trivia on the binding’s value is preserved when possible.
- Scope attachment is automatic when you access values through containers; lower-level helpers such as `function_call_scope` and `set_resolution_context` are internal and may change—avoid depending on them directly.

```python
from nix_manipulator import parse
from nix_manipulator.exceptions import ResolutionError

source = parse("""
let
  a = b;
  b = 3;
in
{
  foo = a;
}
""".strip())

expr = source.expr
assert expr["foo"].value == 3
expr["foo"].value = 10
assert expr.scope["b"].value == 10
```

## Functions and calls

Function definitions use `FunctionDefinition`; calls use `FunctionCall`. Arguments can be identifiers or attribute-set formals.

```python
from nix_manipulator.expressions import (
    AttributeSet,
    Binding,
    BinaryExpression,
    Ellipses,
    FunctionCall,
    FunctionDefinition,
    Identifier,
    Operator,
    Primitive,
)

# x: x + 1
add_one = FunctionDefinition(
    argument_set=Identifier("x"),
    output=BinaryExpression(
        left=Identifier("x"),
        operator=Operator(name="+"),
        right=Primitive(1),
    ),
)
print(add_one.rebuild())  # x: x + 1

# { pname, version, ... }: mkDerivation { ... }
mkdrv = FunctionDefinition(
    argument_set=[Identifier("pname"), Identifier("version"), Ellipses()],
    output=FunctionCall(
        name=Identifier("mkDerivation"),
        argument=AttributeSet.from_dict({"pname": Identifier("pname"), "version": Identifier("version")}),
    ),
)
print(mkdrv.rebuild())
```

Use `FunctionCall(recursive=True, argument=AttributeSet(...))` to emit `f rec { … }`.

## Selection, with, conditionals, and operators

- Attribute selection: `Select(expression=Identifier("pkgs"), attribute="hello", default=Identifier("pkgs.hello"))`.
- With-statements: `WithStatement(environment=Identifier("pkgs"), body=Identifier("hello"))`.
- With inline vs multiline bodies: short bodies stay inline; longer ones expand.

  ```python
  from nix_manipulator.expressions import WithStatement, Identifier, NixList

  print(WithStatement(
      environment=Identifier("lib.maintainers"),
      body=NixList([Identifier("hoh")]),
  ).rebuild())
  # with lib.maintainers; [ hoh ]

  print(WithStatement(
      environment=Identifier("lib.maintainers"),
      body=NixList([Identifier("hoh"), Identifier("mic92")]),
  ).rebuild())
  # with lib.maintainers;
  # [
  #   hoh
  #   mic92
  # ]
  ```
- Conditionals: `IfExpression(condition=..., consequence=..., alternative=...)`.
- Operators: `BinaryExpression(left=..., operator=Operator(name="//"), right=...)` or `UnaryExpression(operator="!", expression=Identifier("x"))`.
- Strings and escaping: string values are escaped automatically (quotes, backslashes, `${` when needed) so programmatic strings stay valid Nix.

  ```python
  from nix_manipulator.expressions import Binding
  print(Binding(name="foo", value='quote "hi" ${name} backslash \\ end\n\t').rebuild())
  # foo = "quote \"hi\" ${name} backslash \\ end\n\t";
  ```

These compose freely inside attrsets, lists, function bodies, and let-expressions.

## Layout and comments

Spacing defaults to sensible RFC-166 output. You can fine-tune layout when needed:

- Most containers expose a `multiline` flag (`AttributeSet`, `NixList`) to force or avoid line breaks.
- Add comments or blank lines via the `before`/`after` fields on any expression, using `Comment("text")`, `MultilineComment("text")`, `linebreak`, or `empty_line` from `nix_manipulator.expressions`.
- Attrsets and lets respect `attrpath_order` when provided; otherwise order follows `values`.

For complex formatting, render with `.rebuild()`, inspect the output, and adjust `before`/`after` trivia as needed. The core rendering is deterministic, so your generated code remains stable across runs.
