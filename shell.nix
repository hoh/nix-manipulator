{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    (pkgs.callPackage ./default.nix { })
    pkgs.python313Packages.pytest
    pkgs.python313Packages.pytest-cov
  ];
}
