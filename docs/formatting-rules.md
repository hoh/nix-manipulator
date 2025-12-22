# Formatting Rules

This document records local normalization choices layered on top of RFC-0166.
It focuses on spacing decisions that are intentionally normalized.

## Sources and precedence

- [RFC-0166](https://github.com/nix-rfc-101/rfcs/blob/master/rfcs/0166-nix-formatting.md) is the primary specification.
- The nixpkgs repository is used as a reference for exhaustive testing of this
  project: [NixOS/nixpkgs](https://github.com/NixOS/nixpkgs/).
- There are a few known cases where formatter output appeared not to follow
  RFC-0166; in those cases, the RFC rules are followed here.

## General spacing normalization

- When the formatter controls spacing between two tokens on the same line, it
  normalizes to either no space or a single space. Multiple spaces or tabs used
  for alignment are collapsed.

- Alignment-only spacing is dropped: horizontal alignment is not preserved.
  Indentation reflects structure, not column alignment.

Examples:
```nix
!   x     # -> ! x
foo    bar # -> foo bar

attr1 = 1;
attr2 = 22;
```

## Token-specific spacing

Binding semicolon spacing: keep the semicolon attached to the value with no
preceding space.

Preferred:
```nix
attr = value;
```
Not:
```nix
attr = value ;
```

Function definition colon spacing: attach the colon to the argument (no space
before `:`).

Preferred:
```nix
name: value: name ++ value
{ pkgs }: pkgs.hello
```
Not:
```nix
name : value
{ pkgs } : pkgs.hello
```

Unary operators: nixfmt formats unary operators with no space between the
operator and its operand, and removes spaces before parenthesized operands.

Example (nixfmt output):
```nix
{
  x = !x;
  y = -x;
  z = !(foo bar);
  a = -(x + y);
  b = -1;
}
```
