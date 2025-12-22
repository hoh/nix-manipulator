# Nix-manipulator (Nima)

A Python library and tools for parsing, manipulating, and reconstructing Nix source code.

## Overview

Started during SaltSprint 2025, Nix-manipulator aims to fill the absence of tools for easily
updating and editing Nix code. 
Popular tools such as [nix-update](https://github.com/Mic92/nix-update) rely on 
[simple string replacement](https://github.com/Mic92/nix-update/blob/fbb35af0ed032ab634c7ef9018320d2370ecfeb1/nix_update/update.py#L26)
or regular expressions for updating Nix code.

## Features and Goals

- **Ease of use** - Simple CLI and API for common operations.
- **High-level abstractions** make manipulating expressions easy.
- **Preserving formatting and comments** in code that respects RFC-0166.

## Non-goals

- Preserving eccentric formatting that does not respect RFC-0166 and would add unnecessary complexity.

## Targeted applications

- Updating values in Nix code by hand, scripts, pipelines, and frameworks.
- Writing refactoring tools.
- Interactive modifications from a REPL.

## Foundations

Nix-manipulator leverages [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
, a multilingual concrete-syntax AST, and its Nix grammar [tree-sitter-nix](https://github.com/nix-community/tree-sitter-nix).

## Project Status

The project is still is in alpha state:

- All Nix syntax is supported
- Test-driven approach prevents regressions
- All Nix files from nixpkgs can be parsed and reproduced*
- CLI and API are still evolving and subject to change

_* with the excption of some expressions that are not RFC-compliant.

## Target Audience

Intermediate Nix users and developers working with Nix code manipulation.

## CLI Usage

Nix-manipulator provides a command-line interface for common operations:

Full docs (MkDocs + Material) live in `docs/` and can be built with:

```shell
nix-build ./docs
```

Serve docs locally:

```shell
nix-shell --run "mkdocs serve"
```

Paths that start with `@` target `let … in` scopes: `@name` edits the innermost scope (creating one if missing), and each extra `@` walks outward; `@foo.bar` applies a dot-path inside that scope. Empty scopes are pruned when their last binding is removed.

Set a value in a Nix file
```shell
nima set -f package.nix version '"1.2.3"'
```

Set a boolean value
```shell
nima set -f package.nix doCheck true
```

Set or update a binding in a scope (auto-creates the innermost scope)
```shell
nima set -f package.nix @bar 2
```

Update an outer scope binding (all scope layers must already exist)
```shell
nima set -f package.nix @@a 10
```

Set a nested binding inside a scope
```shell
nima set -f package.nix @foo.bar '"nested"'
```

Remove an attribute
```shell
nima rm -f package.nix doCheck
```

Remove a scoped binding (pruning the `let` if it becomes empty)
```shell
nima rm -f package.nix @bar
```

Test/validate that a Nix file can be parsed
```shell
nima test -f package.nix
```

## Installation

Install from PyPI:
```shell
pip install nix-manipulator
```

## Development and Testing

Run the small suite (lint + type-check + pytest -m "not nixpkgs") via Nix:
```shell
nix-build
```

Run nixpkgs-marked tests (requires a nixpkgs checkout or NIXPKGS_PATH):
```shell
nix-shell --run "pytest -v -m nixpkgs"
```

## Python Support

The project targets Python 3.13 and ulterior.
Previous versions are not supported.

## Project Links

- Canonical repo (Codeberg): https://codeberg.org/hoh/nix-manipulator
- GitHub mirror: https://github.com/hoh/nix-manipulator

## Contributing

See CONTRIBUTING.md for development guidelines and CODE_OF_CONDUCT.md for
community standards.

## License

Licensed under the GNU Lesser General Public License v3.0 only (LGPL-3.0-only).
