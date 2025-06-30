#!/usr/bin/env python3
"""
High-level example usage of the Nix manipulator library.
"""

from pathlib import Path
from pygments import highlight
from pygments.lexers import PythonLexer, NixLexer
from pygments.formatters import TerminalFormatter
import pprint

from nix_manipulator.converter import convert_nix_source, convert_nix_file

from nix_manipulator.symbols import NixObject


def pretty_print_symbols(obj: NixObject, indent: int = 0) -> str:
    """Pretty print symbol objects in a tree structure."""
    indent_str = "  " * indent

    if hasattr(obj, '__dict__'):
        lines = [f"{indent_str}{obj.__class__.__name__}("]

        for key, value in obj.__dict__.items():
            if key.startswith('_'):
                continue

            if isinstance(value, NixObject):
                lines.append(f"{indent_str}  {key}=")
                lines.append(pretty_print_symbols(value, indent + 2))
            elif isinstance(value, list) and value and isinstance(value[0], NixObject):
                lines.append(f"{indent_str}  {key}=[")
                for item in value:
                    lines.append(pretty_print_symbols(item, indent + 2))
                lines.append(f"{indent_str}  ]")
            elif isinstance(value, dict):
                lines.append(f"{indent_str}  {key}={{")
                for k, v in value.items():
                    if isinstance(v, NixObject):
                        lines.append(f"{indent_str}    {k}=")
                        lines.append(pretty_print_symbols(v, indent + 3))
                    else:
                        lines.append(f"{indent_str}    {k}={repr(v)}")
                lines.append(f"{indent_str}  }}")
            else:
                lines.append(f"{indent_str}  {key}={repr(value)}")

        lines.append(f"{indent_str})")
        return "\n".join(lines)
    else:
        return f"{indent_str}{repr(obj)}"


def main():
    """Main example function."""
    # Example Nix code
    nix_code = '''
{
  lib,
  buildPythonPackage,
  fetchFromGitHub,

  # build-system
  setuptools,
  setuptools-scm,

  # dependencies
  accelerate,
  datasets,
  rich,
  transformers,
}:
let
  owner = "huggingface";
  acc = accelerate;
in
buildPythonPackage rec {
  pname = "trl";
  version = "0.19.0";
  # This is something else
  pyproject = true;

  src = fetchFromGitHub {
    # Something cool
    owner = owner;
    repo = "trl";
    tag = "v${version}";
    hash = "sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=";
  };

  build-system = [
    setuptools
    setuptools-scm
  ];

  /*
    We love
    multiline comments
    here
  */

  dependencies = [
    acc
    datasets
    rich
    transformers
  ];

  # Many tests require internet access.
  doCheck = false;

  pythonImportsCheck = [ "trl" ];

  meta = {
    description = "Train transformer language models with reinforcement learning";
    homepage = "https://github.com/huggingface/trl";
    changelog = "https://github.com/huggingface/trl/releases/tag/${src.tag}";
    license = lib.licenses.asl20;
    maintainers = with lib.maintainers; [ hoh ];
  };
}
'''

    print("🚀 Nix Manipulator Library Example")
    print("=" * 50)

    # Parse Nix code to high-level symbols
    print("\n📊 Converting Nix source to high-level symbols...")
    symbol_tree = convert_nix_source(nix_code)

    if symbol_tree:
        # Pretty print the symbol tree structure
        print("\n🌳 Symbol Tree Structure:")
        print("-" * 30)

        tree_str = pretty_print_symbols(symbol_tree)
        # Highlight with Python syntax (since it looks like Python objects)
        highlighted_tree = highlight(tree_str, PythonLexer(), TerminalFormatter())
        print(highlighted_tree)

        # Reconstruct and display the Nix source code
        print("\n🔧 Reconstructed Nix Source Code:")
        print("-" * 30)

        try:
            reconstructed = symbol_tree.rebuild()
            # Highlight with Nix syntax
            highlighted_nix = highlight(reconstructed, NixLexer(), TerminalFormatter())
            print(highlighted_nix)
        except AttributeError:
            print("❌ Reconstruction not yet fully implemented for this node type")
            print(f"Symbol type: {type(symbol_tree)}")

        # Show some manipulation examples
        print("\n🛠️  Manipulation Examples:")
        print("-" * 30)

        # Example: Modify a value (this is conceptual - actual implementation would depend on the symbol structure)
        print("✨ You can now easily manipulate the Nix code programmatically!")
        print("   - Add/remove dependencies")
        print("   - Modify version numbers")
        print("   - Update URLs and hashes")
        print("   - Add/remove build options")
        print("   - All while preserving comments and formatting!")

    else:
        print("❌ Failed to parse Nix source code")


if __name__ == "__main__":
    main()