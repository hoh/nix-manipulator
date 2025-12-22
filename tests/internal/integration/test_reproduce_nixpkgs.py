"""Tests that parse and rebuild Nix files, including a bulk nixpkgs sweep."""

import difflib
import os
import re
import subprocess
from pathlib import Path

import pytest

from nix_manipulator.parser import parse

TESTS_ROOT = Path(__file__).resolve().parents[2]
_EMPTY_SET_RE = re.compile(r"\{\s*\n\s*\}")
_EMPTY_LIST_RE = re.compile(r"\[\s*\n\s*\]")
RFC_0166_INDENT_NONCOMPLIANT = {
    "nixos/modules/security/apparmor.nix",
    "nixos/modules/services/networking/pangolin.nix",
    "nixos/modules/services/x11/xserver.nix",
    "pkgs/applications/networking/mullvad/mullvad.nix",
    "pkgs/build-support/release/binary-tarball.nix",
    "pkgs/build-support/release/debian-build.nix",
    "pkgs/build-support/release/rpm-build.nix",
    "pkgs/by-name/bl/blahtexml/package.nix",
    "pkgs/by-name/co/codec2/package.nix",
    "pkgs/by-name/en/envision/package.nix",
    "pkgs/by-name/et/eternity/package.nix",
    "pkgs/by-name/ts/tsgolint/package.nix",
    "pkgs/development/beam-modules/mix-release.nix",
    "pkgs/development/interpreters/perl/interpreter.nix",
    "pkgs/development/libraries/glibc/common.nix",
    "pkgs/development/python-modules/graph-tool/default.nix",
    "pkgs/os-specific/bsd/openbsd/pkgs/sys/package.nix",
    "pkgs/tools/package-management/nix/modular/packaging/components.nix",
}

def _patch_indentation_only(source: str, rebuilt: str) -> str | None:
    """Patch indentation-only diffs where indentation changes by 0 or 2 spaces.

    Returns a source variant whose leading whitespace matches `rebuilt` on any
    line where the stripped content is identical. If any line differs after
    stripping, line counts differ, or indentation delta is not 0 or 2 spaces,
    return None to signal a real change.
    """
    source_lines = source.splitlines()
    rebuilt_lines = rebuilt.splitlines()
    if len(source_lines) != len(rebuilt_lines):
        # Structural change (line count) is not an indentation-only diff.
        return None

    patched_lines: list[str] = []
    for idx, (source_line, rebuilt_line) in enumerate(
        zip(source_lines, rebuilt_lines)
    ):
        if source_line == rebuilt_line:
            patched_lines.append(source_line)
            continue
        # Only accept indentation changes; content must match after lstrip.
        if source_line.lstrip() != rebuilt_line.lstrip():
            return None
        source_indent = len(source_line) - len(source_line.lstrip(" "))
        rebuilt_indent = len(rebuilt_line) - len(rebuilt_line.lstrip(" "))
        if abs(rebuilt_indent - source_indent) not in (0, 2):
            return None
        # Keep rebuilt indentation while preserving identical content.
        patched_lines.append(rebuilt_line)
    return "\n".join(patched_lines)


def _collapse_empty_multiline(code: str) -> str:
    """Collapse whitespace-only empty collections to RFC inline forms."""
    collapsed = _EMPTY_SET_RE.sub("{ }", code)
    collapsed = _EMPTY_LIST_RE.sub("[ ]", collapsed)
    return collapsed


def get_nixpkgs_path() -> Path | None:
    """Get the nixpkgs path, with fallback to nix-instantiate command."""
    nixpkgs_path = os.getenv("NIXPKGS_PATH")
    if nixpkgs_path:
        return Path(nixpkgs_path)

    # Check if nix-instantiate is available, else return None
    try:
        # First check if nix-instantiate command exists
        subprocess.run(
            ["nix-instantiate", "--version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return None

    try:
        result = subprocess.run(
            ["nix-instantiate", "--find-file", "nixpkgs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to find nixpkgs path: {e.stderr}") from e
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout while finding nixpkgs path") from None
    except FileNotFoundError:
        raise RuntimeError(
            "nix-instantiate command not found. Make sure Nix is installed."
        ) from None


def _load_curated_nixpkgs_packages():
    """Yield curated entries, skipping blank and commented lines."""
    curated_list_path = TESTS_ROOT / "nixpkgs-curated-packages.txt"
    for line in curated_list_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield stripped


CURATED_NIXPKGS_PACKAGES = list(_load_curated_nixpkgs_packages())


@pytest.mark.nixpkgs
@pytest.mark.parametrize(
    "package",
    CURATED_NIXPKGS_PACKAGES,
    ids=[f"{index}:{path}" for index, path in enumerate(CURATED_NIXPKGS_PACKAGES)],
)
def test_some_nixpkgs_packages(package):
    """Provide a fast sanity check over curated nixpkgs fixtures."""
    # Curated list to keep a small, fast sanity check.
    nixpkgs_path = get_nixpkgs_path()
    if nixpkgs_path is None:
        pytest.skip("NIXPKGS_PATH is not set and nixpkgs is unavailable")
    path = nixpkgs_path / package
    if not path.exists():
        pytest.skip(f"Curated nixpkgs path missing: {package}")
    _assert_reproduced(path)


def _collect_nixpkgs_nix_file_params() -> tuple[Path | None, list[object]]:
    """Collect nixpkgs .nix files and mark long ones as skipped params."""
    pkgs_path = get_nixpkgs_path()
    if pkgs_path is None:
        return None, []
    params = []
    for path in pkgs_path.rglob("*.nix"):
        rel_id = str(path.relative_to(pkgs_path))
        params.append(pytest.param(path, id=rel_id))
    return pkgs_path, params


def _assert_reproduced(path: Path) -> None:
    """Fail with a unified diff when rebuild output diverges."""
    source = path.read_text().strip("\n")
    parsed_cst = parse(source.encode("utf-8"))
    rebuilt_code = parsed_cst.rebuild()
    if NIXPKGS_PATH is not None:
        try:
            rel_path = str(path.relative_to(NIXPKGS_PATH))
        except ValueError:
            rel_path = str(path)
    else:
        rel_path = str(path)
    if rebuilt_code != source:
        if _collapse_empty_multiline(rebuilt_code) == _collapse_empty_multiline(
            source
        ):
            return
        if rel_path in RFC_0166_INDENT_NONCOMPLIANT:
            patched = _patch_indentation_only(source, rebuilt_code)
            if patched == rebuilt_code:
                return
        # Display exact content drift to make failures actionable.
        diff = "".join(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                rebuilt_code.splitlines(keepends=True),
                fromfile=str(path),
                tofile=f"{path} (rebuilt)",
                lineterm="",
            )
        )
        pytest.fail(f"Rebuilt output did not match original for {path}\n{diff}")
    elif rel_path in RFC_0166_INDENT_NONCOMPLIANT:
        pytest.fail(
            "RFC-0166 indentation-noncompliant path now matches rebuild; "
            f"remove from allowlist: {rel_path}"
        )


# Module-level collection so pytest can parametrize tests at import time.
NIXPKGS_PATH, NIXPKGS_PARAMS = _collect_nixpkgs_nix_file_params()


@pytest.mark.nixpkgs
@pytest.mark.parametrize("nix_file", NIXPKGS_PARAMS)
def test_reproduce_all_nixpkgs_packages(nix_file):
    """Parse and rebuild all Nix files in the nixpkgs repository and check if the result is equal to the original."""
    _assert_reproduced(nix_file)
