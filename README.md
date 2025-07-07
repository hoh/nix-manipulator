# Nix-Manipulator

A Python library and tools for parsing, manipulating, and reconstructing Nix source code.

## Features and Goals

- Ease of use.
- High-level abstractions make manipulating expressions easy.
- Preserving formatting and comments in code that respects RFC-166.

## Non-goals

- Preserving eccentric formatting that does not respect RFC-166 and would add unnecessary complexity. 

## Targeted applications

- Updating values in Nix code by hand, scripts, pipelines, and frameworks.
- Writing refactoring tools
- Interactive modifications from a REPL.

## Foundations

Nix-manipulator leverates [tree-sitter], a multilingual AST, and its Nix grammar [tree-sitter-nix].
