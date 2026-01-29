from pathlib import Path

import pytest

from nix_manipulator import parse_file
from nix_manipulator.expressions import Import

HERE = Path(__file__).parent


def test_import_simple():
    """Ensure set_value correctly updates attribute values."""
    source = parse_file(HERE / "simple.nix")
    assert source.rebuild() == "{\n  a = 1;\n  b = import ./set.nix;\n}\n"


def test_import_value():
    source = parse_file(HERE / "simple.nix")
    assert source["a"] == 1
    assert isinstance(source["b"], Import)
    assert source["b"]["c"] == 3


def test_import_value_parenthesized():
    source = parse_file(HERE / "parenthesized.nix")
    assert isinstance(source["b"], Import)
    assert source["b"]["c"] == 3


def test_import_value_requires_nixpath():
    source = parse_file(HERE / "string.nix")
    assert isinstance(source["b"], Import)
    with pytest.raises(TypeError, match="NixPath"):
        _ = source["b"]["c"]
