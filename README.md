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
- **Preserving formatting and comments** in code that respects RFC-166.

## Non-goals

- Preserving eccentric formatting that does not respect RFC-166 and would add unnecessary complexity.

## Targeted applications

- Updating values in Nix code by hand, scripts, pipelines, and frameworks.
- Writing refactoring tools.
- Interactive modifications from a REPL.

## Foundations

Nix-manipulator leverages [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
, a multilingual concrete-syntax AST, and its Nix grammar [tree-sitter-nix](https://github.com/nix-community/tree-sitter-nix).

## Project Status

The project is still in early-stage:

- Not all Nix syntax is supported yet
- Test-driven approach prevents regressions
- CLI and API are still evolving and subject to change
- 28991 / 39573 (73.26%) Nix files from nixpkgs could be parsed and reproduced

## Target Audience

Intermediate Nix users and developers working with Nix code manipulation.

## CLI Usage

Nix-manipulator provides a command-line interface for common operations:

Set a value in a Nix file
```shell
nima set -f package.nix version '"1.2.3"'
```

Set a boolean value
```shell
nima set -f package.nix doCheck true
```

Remove an attribute
```shell
nima rm -f package.nix doCheck
```

Test/validate that a Nix file can be parsed
```shell
nima test -f package.nix
```