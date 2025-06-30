# shell.nix
{ pkgs ? import <nixos-unstable> {} }:

let
  pyEnv = pkgs.python311.withPackages (ps: [
    ps.tree-sitter            # core bindings 0.25.x
    ps.tree-sitter-grammars.tree-sitter-nix        # grammar wrapper → tree_sitter_nix.language()
    ps.tree-sitter-grammars.tree-sitter-python     # grammar wrapper → tree_sitter_python.language()
  ]);
in pkgs.mkShell { packages = [ pkgs.tree-sitter pyEnv ]; }

