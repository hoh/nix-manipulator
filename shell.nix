{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    (pkgs.callPackage ./default.nix { })
    pkgs.python312Packages.pytest
    pkgs.python312Packages.pytest-cov
  ];
}
