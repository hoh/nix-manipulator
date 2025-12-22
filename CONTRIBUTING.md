# Contributing

Thanks for taking the time to contribute to Nix-manipulator.

## Development setup

- Use Nix for a reproducible environment: `nix-shell`
- Run the small suite (lint + type-check + pytest -m "not nixpkgs"):
  `nix-build`
- Run nixpkgs-marked tests (requires a nixpkgs checkout or NIXPKGS_PATH):
  `nix-shell --run "pytest -v -m nixpkgs"`

## Code quality

- Prefer parser/manipulation APIs over ad-hoc string edits to preserve formatting.
- Keep code simple and readable; add tests for new behavior.
- Update docs or CLI help for user-facing changes.

## Submitting changes

- Open issues and pull requests on Codeberg:
  https://codeberg.org/hoh/nix-manipulator/issues
- Keep commits focused and describe the intent of the change.

## License

By contributing, you agree that your contributions are licensed under
the LGPL-3.0 or any later version of the LGPL.
