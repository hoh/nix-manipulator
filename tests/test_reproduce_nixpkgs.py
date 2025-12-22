"""Tests that parse and rebuild Nix files, including a bulk nixpkgs sweep."""

import difflib
import os
import subprocess
from pathlib import Path

import pytest

from nix_manipulator.parser import parse


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
    curated_list_path = Path(__file__).parent / "nixpkgs-curated-packages.txt"
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
    # Curated list to keep a small, fast sanity check.
    _assert_reproduced(get_nixpkgs_path() / package)


def _is_short_nix_file(path: Path, max_lines: int = 300) -> bool:
    """Limit full-sweep tests to smaller files for faster feedback."""
    line_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_count, _ in enumerate(handle, start=1):
            if line_count > max_lines:
                return False
    return True


def _collect_nixpkgs_nix_file_params(
    limit: int = 1_000_000,
) -> tuple[Path | None, list[object]]:
    """Collect nixpkgs .nix files and mark long ones as skipped params."""
    pkgs_path = get_nixpkgs_path()
    if pkgs_path is None:
        return None, []
    params = []
    for path in pkgs_path.rglob("*.nix"):
        rel_id = str(path.relative_to(pkgs_path))
        if _is_short_nix_file(path):
            params.append(pytest.param(path, id=rel_id))
        else:
            # Keep visibility of long files while avoiding heavy runs.
            params.append(
                pytest.param(
                    path,
                    marks=pytest.mark.skip(
                        reason="Skipping files with more than 300 lines"
                    ),
                    id=rel_id,
                )
            )
        if len(params) >= limit:
            break
    return pkgs_path, params


def _assert_reproduced(path: Path) -> None:
    """Fail with a unified diff when rebuild output diverges."""
    source = path.read_text().strip("\n")
    parsed_cst = parse(source.encode("utf-8"))
    rebuilt_code = parsed_cst.rebuild()
    if rebuilt_code != source:
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


# Module-level collection so pytest can parametrize tests at import time.
NIXPKGS_PATH, NIXPKGS_PARAMS = _collect_nixpkgs_nix_file_params()


@pytest.mark.nixpkgs
@pytest.mark.parametrize("nix_file", NIXPKGS_PARAMS)
def test_reproduce_all_nixpkgs_packages(nix_file):
    """Parse and rebuild all Nix files in the nixpkgs repository and check if the result is equal to the original."""
    _assert_reproduced(nix_file)
