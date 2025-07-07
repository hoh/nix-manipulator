from pathlib import Path

from nix_manipulator.parser import parse_nix_cst

NIX_FILES_PATH = Path(__file__).parent


def parse_and_rebuild(source: str):
    parsed_cst = parse_nix_cst(source.encode("utf-8"))
    return parsed_cst.rebuild()


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    rebuilt_code = parse_and_rebuild(source)
    assert source == rebuilt_code


def test_nix_pkgs_simplistic():
    check_package_can_be_reproduced(NIX_FILES_PATH / "nix-files/pkgs/simplistic-01.nix")
