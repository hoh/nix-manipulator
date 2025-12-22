# Nix-manipulator (Nima)

Safely edit Nix code while keeping RFC-166 formatting, comments, and layout intact. Nima parses with tree-sitter-nix and rebuilds code without ad-hoc string replacements.

## What it does

- Preserves RFC-166-friendly formatting and comments; normalizes eccentric layouts.
- Works against parsed syntax trees instead of regex so edits stay structural.
- Understands scoped bindings (`let … in`) and attrpath-derived bindings.
- Shares semantics between the CLI and Python API.

## Install

```bash
pip install nix-manipulator
```

## Fast start (CLI)

- Set a value: `nima set -f package.nix version '"1.2.3"'`
- Remove a binding: `nima rm -f package.nix doCheck`
- Round-trip a file: `nima test -f package.nix` → prints `OK`/`Fail`
- Target scopes with `@` prefixes (innermost) or `@@`/`@@@` (outer scopes): `nima set -f expr.nix @bar 2`

Commands read from stdin by default; `-f FILE` switches the input source and output always goes to stdout. Mutating commands require a single top-level attribute set or a function that returns one (assertions are accepted).

## Fast start (Python)

```python
from nix_manipulator import parse

source = parse('{ version = "0.1.0"; }')
source["version"] = "1.2.3"
print(source.rebuild())
# { version = "1.2.3"; }
```

Nested bindings are edited by chaining mapping access:

```python
source = parse('{ meta = { homepage = "https://old"; }; }')
source["meta"]["homepage"] = "https://example.org"
print(source.rebuild())
```

## Validation

- Small suite (ruff, isort, mypy, pytest -m "not nixpkgs"): `nix-build`
- nixpkgs-marked tests (needs `NIXPKGS_PATH` or a nixpkgs checkout): `nix-shell --run "pytest -v -m nixpkgs"`

## Learn more

- CLI surface and path rules: [CLI guide](cli.md)
- Programmatic usage and mapping helpers: [Python API](api.md)
- Generating new Nix code: [Generation guide](generation.md)
