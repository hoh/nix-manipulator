from pathlib import Path

from nix_manipulator.mapping import tree_sitter_node_to_expression

source_path = Path(__file__).parent / "tests/nix-files/pkgs/simplistic-01.nix"

code = tree_sitter_node_to_expression