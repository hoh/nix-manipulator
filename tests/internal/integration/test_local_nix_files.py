from pathlib import Path

from nix_manipulator.parser import parse
from tests.expressions.trl import nixpkgs_trl_default

TESTS_ROOT = Path(__file__).resolve().parents[2]
NIX_FILES_PATH = TESTS_ROOT / "nix-files"


def parse_and_rebuild(source: str):
    """Centralize parsing so reproduction checks share consistent behavior."""
    parsed_cst = parse(source.encode("utf-8"))
    return parsed_cst.rebuild()


def check_package_can_be_reproduced(path: Path):
    """Assert round-trip fidelity on fixture Nix files."""
    source = path.read_text().strip("\n")
    rebuilt_code = parse_and_rebuild(source)
    assert source == rebuilt_code


def test_nix_pkgs_simplistic():
    """Guard regression on a representative nixpkgs-style file."""
    check_package_can_be_reproduced(NIX_FILES_PATH / "pkgs/simplistic-01.nix")


def test_function_definition():
    """Ensure the TRL fixture rebuilds exactly as stored."""
    function = nixpkgs_trl_default
    source = Path(NIX_FILES_PATH / "pkgs/trl-default.nix").read_text()
    assert function.rebuild() + "\n" == source
