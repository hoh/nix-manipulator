import difflib
import logging
import os
import shutil
import subprocess

import pytest

logger = logging.getLogger(__name__)

def validate_nixfmt_rfc(code: str) -> str:
    """
    Validate that Nix code is RFC-0166 compliant or raise an error.
    """
    if os.getenv("NIXFMT_UNAVAILABLE") in ("true", "1"):
        logger.debug("Nixfmt not available, skipping Nixfmt validation.")
        pytest.skip("nixfmt unavailable; unset NIXFMT_UNAVAILABLE to run formatting validation.")

    nixfmt_bin = shutil.which("nixfmt")
    if not nixfmt_bin:
        raise RuntimeError("nixfmt binary not found in PATH. Set NIXFMT_UNAVAILABLE=1 to disable validation.")

    result = subprocess.run(
        [nixfmt_bin, "--strict", "--verify"],
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "nixfmt exited with a non-zero status."
        raise AssertionError(f"nixfmt failed to validate code: {details}")

    expected = code.rstrip("\n")
    formatted = result.stdout.rstrip("\n")
    if formatted != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                formatted.splitlines(keepends=True),
                fromfile="expected",
                tofile="nixfmt",
                lineterm="",
            )
        )
        raise AssertionError(f"nixfmt output differs from input:\n{diff}")

    return code
