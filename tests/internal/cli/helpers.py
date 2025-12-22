from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def transform_with_cli(nix_code: str, command: list[str]) -> str:
    """Transform Nix code using the command-line interface using stdin."""
    cli_args = [sys.executable, "-m", "nix_manipulator", *command]

    env = os.environ.copy()
    pythonpath_entries = [str(PROJECT_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    result = subprocess.run(
        cli_args,
        input=nix_code,
        text=True,
        capture_output=True,
        cwd=PROJECT_ROOT,
        check=False,
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"nima {' '.join(command)} failed: {details}")

    return result.stdout.rstrip("\n")
