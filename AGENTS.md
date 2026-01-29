# AGENTS.md

## Project
Nix-manipulator (nima) is a Python library and CLI for parsing, manipulating, and rebuilding Nix code while preserving RFC-166 formatting via tree-sitter-nix.

## Goals and values
- Ease of use via simple CLI and API.
- High-level abstractions for editing expressions safely.
- Preserve formatting and comments in RFC-166-compliant code.
- Do not preserve eccentric, non-RFC-166 formatting.
- Attribute path order within an attribute set matters for RFC-166 output; retain it during parsing and rewrites.

## Layout
- `nix_manipulator/`: core library and CLI entrypoints (`cli.py`, `__main__.py`).
- `nix_manipulator/expressions/`: AST node types and helpers.
- `tests/`: pytest suite and fixtures (see `tests/nix-files/`).
- `pyproject.toml`: build metadata and hatch scripts.

## Commands
- `nix-build`: run the small suite via the default Nix check phase (ruff/isort/mypy + pytest -m "not nixpkgs").
- `nix-shell --run "pytest -v -m nixpkgs"`: run the nixpkgs-marked tests for full validation. Use 300 seconds timeout. Add "-x" when it is relevant to stop on first failure.

## Tooling
You can use anything from `nixpkgs` using `nix-shell` or by modifying `shell.nix`.
Never create virtualenv or use other software than Nix to fetch or install software.

## Testing notes
- Always run the small test suite followed by the nixpkgs-marked tests for full validation when the small suite passes.
- Tests marked `nixpkgs` require a nixpkgs checkout. Set `NIXPKGS_PATH` or ensure `nix-instantiate` is available.
- Agents should always run tests via Nix; choose either the small suite or the nixpkgs-marked tests for full validation.
- Ignore the `<nixpkgs>` channel warning from `nix-shell`; it may fall back to the ambient environment while still running the tests.

## Conventions
- Target Python 3.13.
- Prefer parser/manipulation APIs over ad-hoc string edits to keep formatting stable.
- Keep code simple. No import magic, limit the use of complex patterns but take advantage of syntax like `match`, comprehensions and generators.

## Agent notes
- When making changes in the code, use `./agent-notes/README.md` to track current/prior tasks, plans, todos, and notes; agents own these files.
