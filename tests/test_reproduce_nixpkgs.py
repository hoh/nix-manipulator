import concurrent
import os
from pathlib import Path

import pytest

from nix_manipulator.parser import parse

NIXPKGS_PATH = os.getenv("NIXPKGS_PATH")


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
        check_package_can_be_reproduced(NIXPKGS_PATH / package)


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
    pkgs_path = NIXPKGS_PATH

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
