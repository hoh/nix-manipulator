#!/usr/bin/env python3
"""
nix-diff.py - Compare processed attributes of two Nix files and return differences.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any

from serializor import flatten_nix_file, parse_nix_value


def compare_nix_files(file1_path: Paath, file2_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Compare processed attributes of two Nix files and return differences.

    Args:
        file1_path: Path to the first Nix file
        file2_path: Path to the second Nix file

    Returns:
        Dictionary with structure:
        {
            "added": {key: value},      # Keys present in file2 but not in file1
            "removed": {key: value},    # Keys present in file1 but not in file2
            "modified": {key: {"old": old_value, "new": new_value}}  # Keys with different values
        }
    """
    # Process both files
    file1_raw = flatten_nix_file(file1_path)
    file2_raw = flatten_nix_file(file2_path)

    file1_attrs = {key: parse_nix_value(value) for key, value in file1_raw.items()}
    file2_attrs = {key: parse_nix_value(value) for key, value in file2_raw.items()}

    # Find differences
    file1_keys = set(file1_attrs.keys())
    file2_keys = set(file2_attrs.keys())

    added = {key: file2_attrs[key] for key in file2_keys - file1_keys}
    removed = {key: file1_attrs[key] for key in file1_keys - file2_keys}

    common_keys = file1_keys & file2_keys
    modified = {}

    for key in common_keys:
        if file1_attrs[key] != file2_attrs[key]:
            modified[key] = {
                "old": file1_attrs[key],
                "new": file2_attrs[key]
            }

    return {
        "added": added,
        "removed": removed,
        "modified": modified
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
        # Compare the files and get the differences data structure
        differences = compare_nix_files(Path(args.file1), Path(args.file2))

        # Print as JSON with indent 4
        print(json.dumps(differences, indent=4))

    except Exception as e:
        error_result = {"error": str(e)}
        print(json.dumps(error_result, indent=4))
        return 1

    return 0


if __name__ == "__main__":
    exit(main())