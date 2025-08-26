{ pkgs ? import <nixpkgs> {} }:
let
  python = pkgs.python312Packages;
  pytestCheckHook = python.pytestCheckHook;
in
python.buildPythonPackage rec {
  pname = "nix-manipulator";
  version = "0.1.0";

  format = "pyproject";
  nativeBuildInputs = [ python.hatchling ];

  src = ./.;

  propagatedBuildInputs = with python; [
    tree-sitter
    tree-sitter-grammars.tree-sitter-nix
    pydantic
    pygments
  ];

  doCheck = true;

  nativeCheckInputs = [
    pytestCheckHook
  ];

  checkPhase = ''
    pytest -v -m "not nixpkgs"
  '';

  disabledTests = [
    "test_some_nixpkgs_packages"
  ];

  pythonImportsCheck = [ "nix_manipulator" ];

  meta = with pkgs.lib; {
    description  = "A Python library for parsing, manipulating, and reconstructing Nix source code";
    homepage     = "https://codeberg.org/hoh/nix-manipulator";
    license      = licenses.agpl3Only;
    maintainers  = with maintainers; [ hoh ];
  };
}
