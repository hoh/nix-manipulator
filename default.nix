{
  pkgs ? import <nixpkgs> { },
}:
let
  python = pkgs.python312Packages;
in
python.callPackage ./nix-manipulator.nix { }
