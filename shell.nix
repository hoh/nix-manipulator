{
  pkgs ? import <nixpkgs> { },
}:

pkgs.mkShell {
  packages = [
    (pkgs.callPackage ./default.nix { })
    pkgs.python312Packages.pytest
    pkgs.python312Packages.pytest-cov
  ];
}
