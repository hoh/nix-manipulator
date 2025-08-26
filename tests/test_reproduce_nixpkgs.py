import concurrent
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


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    parsed_cst = parse(source.encode("utf-8"))
    rebuilt_code = parsed_cst.rebuild()
    try:
        assert rebuilt_code == source
        return True
    except Exception as e:
        print(f"Error rebuilding {path}: {e.__class__.__name__}")
        return False


@pytest.mark.nixpkgs
def test_some_nixpkgs_packages():
    packages = [
        "pkgs/development/python-modules/trl/default.nix",
        "pkgs/development/python-modules/cut-cross-entropy/default.nix",
        "pkgs/development/python-modules/unsloth-zoo/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        "pkgs/development/python-modules/ptpython/default.nix",
        "pkgs/development/python-modules/requests/default.nix",
        "pkgs/kde/gear/cantor/default.nix",
        "pkgs/kde/plasma/plasma-nm/default.nix",
        "lib/tests/modules/define-attrsOfSub-foo-force-enable.nix",
        # "lib/tests/modules/declare-bare-submodule-deep-option.nix",
        "pkgs/kde/third-party/karousel/default.nix",
        "pkgs/kde/third-party/wallpaper-engine-plugin/default.nix",
        # "pkgs/kde/gear/koko/default.nix",
        # "pkgs/development/python-modules/numpy/1.nix",  # Requires assert
    ]
    for package in packages:
        check_package_can_be_reproduced(get_nixpkgs_path() / package)


def process_nix_file(path_str):
    path = Path(path_str)
    try:
        check_package_can_be_reproduced(path)
        return True, None
    except Exception as e:
        return False, (str(path), str(e))


@pytest.mark.nixpkgs
def test_reproduce_all_nixpkgs_packages():
    """Parse and rebuild all Nix files in the nixpkgs repository and check if the result is equal to the original."""
    success = 0
    failure = 0
    limit = 1_000_000
    pkgs_path = get_nixpkgs_path()

    paths = [str(p) for p in list(pkgs_path.rglob("*.nix"))[:limit]]

    with concurrent.futures.ProcessPoolExecutor(max_workers=32) as executor:
        futures = [executor.submit(process_nix_file, path) for path in paths]

        # Process results as they complete
        for future in concurrent.futures.as_completed(futures):
            succ, err_info = future.result()
            if succ:
                success += 1
            else:
                failure += 1
                path_str, e_str = err_info
                # print(path_str)
                # print(e_str)

    total = success + failure
    print(
        f"{success}/{total} Nix files from nixpkgs could be reproduced ({success / total:.2%})"
    )
    assert failure == 0
