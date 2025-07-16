from pathlib import Path

from nix_manipulator.parser import parse

NIXPKGS_PATH = Path("/home/sepal/Repos/hoh/nixpkgs")


def check_package_can_be_reproduced(path: Path):
    source = path.read_text().strip("\n")
    parsed_cst = parse(source.encode("utf-8"))
    rebuilt_code = parsed_cst.rebuild()
    try:
        assert rebuilt_code == source
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
        "pkgs/development/python-modules/ptpython/default.nix",
        "pkgs/development/python-modules/requests/default.nix",
        "pkgs/kde/gear/cantor/default.nix",
        "pkgs/kde/plasma/plasma-nm/default.nix",
        # "pkgs/kde/gear/koko/default.nix",
        # "pkgs/development/python-modules/numpy/1.nix",  # Requires assert
    ]
    for package in packages:
        check_package_can_be_reproduced(NIXPKGS_PATH / package)


def test_all_nixpkgs_packages():
    success = 0
    failure = 0
    limit = 100000
    # pkgs_paths = NIXPKGS_PATH / "pkgs/development/python-modules"
    pkgs_path = NIXPKGS_PATH

    for i, path in enumerate(pkgs_path.rglob("*.nix")):
        try:
            check_package_can_be_reproduced(path)
            success += 1
        except Exception as e:
            print(path)
            print(e)
            failure += 1
        if i >= limit:
            break

    total = success + failure
    print(
        f"{success}/{total} Nix files from nixpkgs could be reproduced ({success / total:.2%})"
    )
    assert False
