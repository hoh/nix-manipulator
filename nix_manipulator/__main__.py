#!/usr/bin/env python3
"""CLI entrypoint wrapper."""

from nix_manipulator.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
