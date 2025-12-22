# Python API

Nima provides a small, mapping-style API for manipulating parsed Nix code while preserving RFC-166 formatting and comments. All edits operate on syntax trees produced by tree-sitter-nix; no string hacking is involved.

For CLI usage and `@` scope selectors, see the [CLI guide](cli.md). For building new Nix sources from scratch, see the [Generation guide](generation.md).

## Core imports

```python
from nix_manipulator import parse, parse_file
from nix_manipulator.expressions import NixSourceCode
```

- `parse(source: str) -> NixSourceCode`: parse a string into a manipulable source object.
- `parse_file(path: str | Path) -> NixSourceCode`: parse from disk.
- `.rebuild() -> str`: render parsed objects back to RFC-166 text.
  (`contains_error` exists for internal diagnostics and is not a stable API.)

## Parse from disk

```python
from pathlib import Path
from nix_manipulator import parse_file

path = Path("package.nix")
src = parse_file(path)
src["version"] = "1.2.3"
path.write_text(src.rebuild())
```

## Editing attribute sets

`NixSourceCode` behaves like a mapping that targets the single top-level attribute set (or a function returning one). If the input does not meet that shape, attempts to edit raise `ValueError`.

```python
src = parse('{ version = "0.1.0"; }')
src["version"] = "1.2.3"
print(src.rebuild())
# { version = "1.2.3"; }

del src["version"]
print(src.rebuild())
# { }
```

Nested sets work naturally when the binding already holds an attrset:

```python
src = parse("{ foo = { bar = 1; }; }")
src["foo"]["bar"] = 2
print(src.rebuild())
# { foo = { bar = 2; }; }
```

Attrpath-derived bindings are preserved: updating `src["foo"]["bar"]` respects existing attrpath layout, and deleting the final attrpath leaf prunes its root.

When you need to reference a name instead of a string literal, use `Identifier`:

```python
from nix_manipulator.expressions import Identifier

src = parse('{ src = null; }')
src["src"] = Identifier("fetchurl")
print(src.rebuild())
# { src = fetchurl; }
```

## Working with scopes

Scopes live on the underlying `AttributeSet` objects. When you parse code, grab the single top-level attrset and edit its `.scope` mapping (which represents the innermost `let … in` layer). Assignments create that innermost scope when needed; removing the last binding unwraps the empty `let`.

```python
src = parse("{ foo = 1; }")
target = src.expr  # top-level AttributeSet
target.scope["bar"] = 2
print(src.rebuild())
# let
#   bar = 2;
# in
# { foo = 1; }
```

Outer scopes are stored in `target.scope_stack` (outermost first). Those layers are low-level; prefer the CLI helpers for multi-layer scope rewrites when possible.

Resolution context attaches automatically when you traverse through containers (`src["foo"]`, `attrset["bar"]`, etc.). Lower-level helpers such as `set_resolution_context` and `function_call_scope` are internal wiring and not part of the stable API.

## Constructing attrsets directly

Lower-level helpers live in `nix_manipulator.expressions`. For example, to build an attrset with an existing scope:

```python
from nix_manipulator.expressions import AttributeSet, Binding

source = AttributeSet({"foo": 1}, scope=[Binding(name="bar", value=2)])
source.scope["bar"] = 3
print(source.rebuild())
# let
#   bar = 3;
# in
# { foo = 1; }
```

## Error signaling

- `KeyError`: missing binding, missing nested attribute, or missing scope layer when traversing outward.
- `ValueError`: empty/invalid identifier segments, assigning into a non-attrset value, attempting to overwrite an attrpath root with a simple binding, or providing a value that does not parse as a single expression.

## CLI helpers

CLI-specific helpers (`set_value`, `remove_value`) exist for parity with `nima set`/`nima rm`, but they are not part of the stable public API. Prefer direct mapping operations plus `.rebuild()` for long-term compatibility.

## Internal helpers (unstable)

The project exposes some wiring functions for its own implementations. These are not stable public APIs and may change without notice:

- Parsing diagnostics: `parse_to_ast` (not exported) and `NixSourceCode.contains_error`.
- Resolution plumbing in `nix_manipulator.resolution`: `function_call_scope`, `attach_resolution_context`, `set_resolution_context`, `clear_resolution_context`, `scopes_for_owner`, and related context helpers.
- CLI plumbing in `nix_manipulator.cli.manipulations`: `_resolve_target_set*`, `_collect_scope_layers`, `_write_scope_layers`, and the `set_value`/`remove_value` helpers (CLI parity only).
- Formatting utilities in `nix_manipulator.expressions.trivia` and attrpath helpers in `nix_manipulator.expressions.set` (e.g., `_split_attrpath`, `_merge_attrpath_bindings`, `_expand_attrpath_binding`).
- Recursive attrsets: use `AttributeSet(recursive=True)`; the old `RecursiveAttributeSet` wrapper has been removed.

When in doubt, stick to the mapping-style API (`parse`, `parse_file`, `NixSourceCode`, attribute access) instead of calling these internals directly.
