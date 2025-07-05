from pathlib import Path

from nix_manipulator.cst.parser import parse_nix_cst

NIXPKGS_PATH = Path("/home/sepal/Repos/hoh/nixpkgs")


def parse_and_rebuild(source: str):
    parsed_cst = parse_nix_cst(source.encode("utf-8"))
    return parsed_cst.rebuild()


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    rebuilt_code = parse_and_rebuild(source)
    assert source == rebuilt_code


def test_some_nixpkgs_packages():
    packages = [
        "pkgs/development/python-modules/trl/default.nix",
        "pkgs/development/python-modules/cut-cross-entropy/default.nix",
        "pkgs/development/python-modules/unsloth-zoo/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        "pkgs/development/python-modules/ptpython/default.nix",
    ]
    for package in packages:
        check_package_can_be_reproduced(NIXPKGS_PATH / package)
