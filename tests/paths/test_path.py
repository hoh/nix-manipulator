from pathlib import Path

from nix_manipulator import parse_file
from nix_manipulator.expressions import NixPath

HERE = Path(__file__).parent


def test_path_simple():
    """Ensure a file can contain an import instruction."""
    source = parse_file(HERE / "simple.nix")
    assert source["text"] == NixPath("./text.txt")


def test_path_content():
    """Ensure a file can contain an import instruction."""
    source = parse_file(HERE / "simple.nix")
    assert b"My crime is that of curiosity" in source["text"].value
    assert "My crime is that of curiosity" in source["text"].text
