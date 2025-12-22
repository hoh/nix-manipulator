# CLI guide

Nima’s CLI performs structural edits on parsed Nix expressions while preserving RFC-166 formatting and comments.

## Basics

- Syntax: `nima <command> [options]`; all commands read from stdin unless `-f FILE` is provided and write results to stdout.
- Mutating commands expect exactly one top-level expression: an attribute set, a function that returns one (including `let … in`), or an assertion wrapping either. Inputs that do not match error out instead of guessing.
- Errors from parsing or invalid paths exit non-zero; `test` reports round-trip success via `OK`/`Fail` and exits `0`/`1`.

## Commands

- `set NPATH VALUE` — add or replace a binding; honors attrpaths and scope selectors.
- `rm NPATH` — remove a binding; prunes empty scopes and attrpath nodes.
- `test` — parse and rebuild; prints `OK`/`Fail` and exits `0`/`1`.
- `shell` — drop into a Python REPL with `parse`, `set_value`, `remove_value`, and `NixSourceCode` preloaded; when `-f FILE` is given, `source_text`/`source` are pre-seeded.

### Options

- `-f, --file FILE` — read input from `FILE` instead of stdin (all commands).

## NPath syntax (set/rm)

- Dot-delimited identifiers: `foo.bar.baz`. Identifiers accept letters, digits, underscores, apostrophes, and hyphens (not as the first character).
- Quote segments containing dots or special characters: `foo."bar.baz"`; escape quotes or backslashes inside (`"bar\\\"baz"`).
- Paths always name a binding; empty paths are rejected.
- Attrpaths are preserved: if a root attrpath exists (`foo.bar = 1;`), `nima set foo.baz 2` keeps the attrpath layout and removing the last attrpath leaf prunes the root. Overwriting an attrpath root with an explicit binding errors.
- Values must parse as a single Nix expression; invalid values abort without emitting partial output.

## Scope selectors

- Prefix `@` to target `let … in` scopes. `@name` edits the **innermost** scope; `@@name` targets the next outer scope, `@@@` the one after that, and so on.
- Scoped paths compose with dot-paths: `@foo.bar` edits `bar` inside the innermost scope binding `foo`.
- Assigning to `@name` creates the innermost scope if it does not exist. Deeper scopes (`@@`, `@@@`, …) must already exist.
- When `rm` empties a scope, the `let … in` wrapper is removed.

## Examples (before → after)

Each block shows the original file, the command that was run, and the rebuilt output.

Set a version:

```text
{ version = "0.1.0"; }
$ nima set -f expr.nix version '"1.2.3"'
{ version = "1.2.3"; }
```

Create a scope on demand:

```text
{ foo = 1; }
$ nima set -f expr.nix @bar 2
let
  bar = 2;
in
{ foo = 1; }
```

Remove a scoped binding and prune the empty `let`:

```text
let
  bar = 2;
in
{ foo = 1; }
$ nima rm -f expr.nix @bar
{ foo = 1; }
```

Update an outer scope binding:

```text
let
  a = 1;
in
let
  b = 2;
in
{ c = a + b; }
$ nima set -f expr.nix @@a 10
let
  a = 10;
in
let
  b = 2;
in
{ c = a + b; }
```

Edit a nested binding inside a scope:

```text
let
  foo = { bar = 1; baz = 3; };
in
{ }
$ nima set -f expr.nix @foo.bar 2
let
  foo = { bar = 2; baz = 3; };
in
{ }
```

Set a binding with a quoted segment (attribute names containing dots or special characters):

```text
{ foo = { "bar.baz" = 1; }; }
$ nima set -f expr.nix foo."bar.baz" 2
{ foo = { "bar.baz" = 2; }; }
```

Read from stdin and write to stdout:

```text
$ printf '{ version = "0.1.0"; }\n' | nima set version '"1.2.3"'
{ version = "1.2.3"; }
```
