{
  lib,
  python3Packages,
}:

python3Packages.buildPythonPackage {
  pname = "nix-manipulator";
  version = "0.1.2";
  pyproject = true;

  src = ../../../.;

  build-system = with python3Packages; [
    hatchling
    hatch-vcs
  ];

  dependencies = with python3Packages; [
    tree-sitter
    tree-sitter-grammars.tree-sitter-nix
    pydantic
    pydantic-core
    pygments
  ];

  nativeCheckInputs = with python3Packages; [ pytestCheckHook ];

  pythonImportsCheck = [ "nix_manipulator" ];

  pytestFlagsArray = [
    "-v"
    "-m 'not nixpkgs'"
  ];

  disabledTests = [
    "test_some_nixpkgs_packages"
  ];

  meta = {
    description = "Python library for parsing, manipulating, and reconstructing Nix source code";
    homepage = "https://codeberg.org/hoh/nix-manipulator";
    license = lib.licenses.agpl3Only;
    maintainers = with lib.maintainers; [ hoh ];
    mainProgram = "nima";
  };
}
