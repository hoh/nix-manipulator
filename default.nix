{ pkgs ? import <nixpkgs> {} }:

pkgs.buildPythonPackage rec {
  pname = "nix-manipulator";
  version = "0.1.0";

  src = pkgs.fetchFromGitHub {
    owner = "hoh";
    repo = "nix-manipulator";
    rev = "cf15618"; # Git hash from your commit
    sha256 = "sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ="; # Replace with actual hash
    fetchSubmodules = true;
    inherit git;
  };

  propagatedBuildInputs = [
    pkgs.python3Packages.tree-sitter
    pkgs.python3Packages.tree-sitter-nix
    pkgs.python3Packages.pydantic
    pkgs.python3Packages.pygments
  ];

  doCheck = false; # Set to true if you want to run tests

  meta = with pkgs.lib; {
    description = "A Python library for parsing, manipulating, and reconstructing Nix source code";
    homepage = "https://codeberg.org/hoh/nix-manipulator";
    license = licenses.agpl3;
    maintainers = with maintainers; [ hoh ];
  };
}
