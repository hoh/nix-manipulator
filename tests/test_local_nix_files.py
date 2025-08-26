from pathlib import Path

from nix_manipulator.parser import parse
from tests.expressions.trl import nixpkgs_trl_default

NIX_FILES_PATH = Path(__file__).parent


def parse_and_rebuild(source: str):
    parsed_cst = parse(source.encode("utf-8"))
    return parsed_cst.rebuild()


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    rebuilt_code = parse_and_rebuild(source)
    assert source == rebuilt_code


def test_nix_pkgs_simplistic():
    check_package_can_be_reproduced(NIX_FILES_PATH / "nix-files/pkgs/simplistic-01.nix")


def test_function_definition():
    function = nixpkgs_trl_default
    source = Path(NIX_FILES_PATH / "nix-files/pkgs/trl-default.nix").read_text()
    assert function.rebuild() + "\n" == source
