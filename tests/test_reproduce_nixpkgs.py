from pathlib import Path

from nix_manipulator.parser import parse_nix_cst

NIXPKGS_PATH = Path("/home/sepal/Repos/hoh/nixpkgs")


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    parsed_cst = parse_nix_cst(source.encode("utf-8"))
    rebuilt_code = parsed_cst.rebuild()
    try:
        assert source == rebuilt_code
    except:
        print(parsed_cst)
        raise


def test_some_nixpkgs_packages():
    packages = [
        "pkgs/development/python-modules/trl/default.nix",
        "pkgs/development/python-modules/cut-cross-entropy/default.nix",
        "pkgs/development/python-modules/unsloth-zoo/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        "pkgs/development/python-modules/unsloth/default.nix",
        # "pkgs/development/python-modules/ptpython/default.nix",
    ]
    for package in packages:
        check_package_can_be_reproduced(NIXPKGS_PATH / package)
