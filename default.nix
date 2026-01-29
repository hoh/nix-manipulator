{ pkgs ? import (builtins.fetchTarball {
  # url = "https://github.com/NixOS/nixpkgs/archive/ecdb2e3a81213177cde9ce769e5f086ff24387b6.tar.gz";
  url = "https://github.com/hoh/nixpkgs/archive/refs/heads/fix-rfc-0166-compliance.tar.gz";
}) {} }:
let
  python = pkgs.python313Packages;
  pytestCheckHook = python.pytestCheckHook;
in
python.buildPythonPackage rec {
  pname = "nix-manipulator";
  version = "0.1.2";

  format = "pyproject";
  nativeBuildInputs = [ python.hatchling python.hatch-vcs ];

  src = ./.;

  propagatedBuildInputs = with python; [
    tree-sitter
    tree-sitter-grammars.tree-sitter-nix
    pygments
  ];

  postPatch = ''
    rm -rf dist
  '';

  doCheck = true;

  nativeCheckInputs = [
    pytestCheckHook
    python.pytest-cov
    python.ruff
    python.mypy
    python.isort
    pkgs.nixfmt
  ];

  checkPhase = ''
    ruff check nix_manipulator tests
    ruff format --check nix_manipulator tests
    mypy --ignore-missing-imports nix_manipulator
    pytest -v --cov=nix_manipulator --cov-report=term-missing --cov-fail-under=98 -m "not nixpkgs"
  '';

  disabledTests = [
    "test_some_nixpkgs_packages"
  ];

  pythonImportsCheck = [ "nix_manipulator" ];

  meta = with pkgs.lib; {
    description  = "A Python library for parsing, manipulating, and reconstructing Nix source code";
    homepage     = "https://codeberg.org/hoh/nix-manipulator";
    license      = licenses.lgpl3Only or licenses.lgpl3;
    maintainers  = with maintainers; [ hoh ];
  };
}
