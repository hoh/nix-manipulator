#!/usr/bin/env python3
"""
nix-diff.py - Compare processed attributes of two Nix files and return differences.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

from serializor import flatten_nix_file, parse_nix_value


def compare_nix_files(file1_path: Path, file2_path: Path) -> Dict[str, Dict[str, Any]]:
    """Compare processed attributes of two Nix files and return differences."""
    # Process both files in one step
    file1_attrs = {k: parse_nix_value(v) for k, v in flatten_nix_file(file1_path).items()}
    file2_attrs = {k: parse_nix_value(v) for k, v in flatten_nix_file(file2_path).items()}

    # Get key sets
    keys1, keys2 = set(file1_attrs), set(file2_attrs)

    # Build result dictionary
    return {
        "added": {k: file2_attrs[k] for k in keys2 - keys1},
        "removed": {k: file1_attrs[k] for k in keys1 - keys2},
        "modified": {
            k: {"old": file1_attrs[k], "new": file2_attrs[k]}
            for k in keys1 & keys2
            if file1_attrs[k] != file2_attrs[k]
        }
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare processed attributes of two Nix files and show differences"
    )
    parser.add_argument("file1", help="Path to the first Nix file")
    parser.add_argument("file2", help="Path to the second Nix file")
    args = parser.parse_args()

    try:
        differences = compare_nix_files(Path(args.file1), Path(args.file2))
        print(json.dumps(differences, indent=4))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=4))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())