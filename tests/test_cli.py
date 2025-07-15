from pathlib import Path

from nix_manipulator.__main__ import main


def test_cli_set_boolean(capsys):
    result = main(
        ["set", "-f", "tests/nix-files/pkgs/simplistic-01.nix", "doCheck", "true"]
    )
    original = Path("tests/nix-files/pkgs/simplistic-01.nix").read_text().strip("\n")
    assert result == original.replace("doCheck = false;", "doCheck = true;")


def test_cli_set_string(capsys):
    result = main(
        ["set", "-f", "tests/nix-files/pkgs/simplistic-01.nix", "version", '"1.2.3"']
    )
    original = Path("tests/nix-files/pkgs/simplistic-01.nix").read_text().strip("\n")
    assert result == original.replace('version = "0.15.2";', 'version = "1.2.3";')


def test_cli_test(capsys):
    result = main(
        ["test", "-f", "tests/nix-files/pkgs/simplistic-01.nix"]
    )
    assert result == "OK"