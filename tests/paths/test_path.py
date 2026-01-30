import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

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


def test_update_path():
    template = HERE / "simple.nix"
    with TemporaryDirectory() as tmp_dir:
        file_path = Path(tmp_dir) / "simple.nix"
        shutil.copyfile(template, file_path)

        source = parse_file(file_path)
        source["quote"] = "This is our world now..."
        source.save()

        assert 'quote = "This is our world now...";' in file_path.read_text()
