{ pkgs ? import <nixpkgs> {} }:
let
  python = pkgs.python312Packages;
in
python.buildPythonPackage rec {
  pname = "nix-manipulator";
  version = "0.1.0";

  format = "pyproject";
  nativeBuildInputs = [ python.hatchling ];

#  src = pkgs.fetchFromGitea {
#    domain = "codeberg.org";
#    owner  = "hoh";
#    repo   = "nix-manipulator";
#    rev    = "dcf9603195c1332c3b8b3bc6afa5c33701f56ae0";
#    hash   = "";
#  };
  src = ./.;

  propagatedBuildInputs = with python; [
    tree-sitter
    tree-sitter-grammars.tree-sitter-nix
    pydantic
    pygments
  ];

  doCheck = true;
  installCheckPhase = ''command -v $out/bin/nima'';

  meta = with pkgs.lib; {
    description  = "A Python library for parsing, manipulating, and reconstructing Nix source code";
    homepage     = "https://codeberg.org/hoh/nix-manipulator";
    license      = licenses.agpl3Only;
    maintainers  = with maintainers; [ hoh ];
  };
}
