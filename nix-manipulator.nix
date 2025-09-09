{
  lib,
  buildPythonPackage,
  hatchling,
  hatch-vcs,
  tree-sitter,
  tree-sitter-grammars,
  pydantic,
  pydantic-core,
  pygments,
  pytestCheckHook,
}:

buildPythonPackage {
  pname = "nix-manipulator";
  version = "0.1.2";
  pyproject = true;

  src = ./.;

  build-system = [
    hatchling
    hatch-vcs
  ];

  dependencies = [
    tree-sitter
    tree-sitter-grammars.tree-sitter-nix
    pydantic
    pydantic-core
    pygments
  ];

  nativeCheckInputs = [ pytestCheckHook ];

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
