#!/usr/bin/env python3
"""
Benchmark the Nix parsing/rebuild pipeline with stage-level timings.

Emits JSON lines so results are easy to aggregate.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Iterable

from tree_sitter import Node

from nix_manipulator.expressions.source_code import NixSourceCode
from nix_manipulator.parser import parse_to_ast


def count_nodes(root: Node) -> int:
    """Count all tree-sitter nodes in a CST."""
    count = 0
    stack = [root]
    while stack:
        node = stack.pop()
        count += 1
        stack.extend(node.children)
    return count


def iter_paths(paths: Iterable[str], list_file: Path | None, base_dir: Path | None):
    """Normalize input paths so benchmarks cover consistent file sets."""
    collected: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            collected.extend(sorted(path.rglob("*.nix")))
        else:
            collected.append(path)

    if list_file is not None:
        lines = list_file.read_text().splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            listed = Path(stripped)
            if not listed.is_absolute() and base_dir is not None:
                listed = base_dir / listed
            collected.append(listed)

    return [path for path in collected if path.exists()]


def run_once(path: Path, mode: str, *, include_counts: bool) -> dict[str, object]:
    """Time a single pipeline pass to provide repeatable benchmarking data."""
    result: dict[str, object] = {"path": str(path)}
    t0 = time.perf_counter()
    data = path.read_bytes()
    t1 = time.perf_counter()
    root = parse_to_ast(data)
    t2 = time.perf_counter()

    result["read_s"] = t1 - t0
    result["parse_cst_s"] = t2 - t1
    result["input_bytes"] = len(data)
    result["input_lines"] = data.count(b"\n") + (1 if data else 0)

    if include_counts:
        count_start = time.perf_counter()
        result["cst_nodes"] = count_nodes(root)
        result["count_nodes_s"] = time.perf_counter() - count_start

    if mode in {"parse-model", "roundtrip"}:
        model_start = time.perf_counter()
        model = NixSourceCode.from_cst(root)
        model_end = time.perf_counter()
        result["model_s"] = model_end - model_start
    else:
        model = None

    if mode == "roundtrip":
        rebuild_start = time.perf_counter()
        rebuilt = model.rebuild() if model is not None else ""
        rebuild_end = time.perf_counter()
        result["rebuild_s"] = rebuild_end - rebuild_start
        result["output_bytes"] = len(rebuilt.encode("utf-8"))

    result["total_s"] = time.perf_counter() - t0
    return result


def main() -> int:
    """Expose a CLI entrypoint so benchmarks are easy to automate."""
    parser = argparse.ArgumentParser(
        description="Benchmark parsing/rebuild stages with JSON lines output."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to benchmark (directories are searched for *.nix).",
    )
    parser.add_argument(
        "--list-file",
        type=Path,
        help="Optional file containing paths to benchmark (one per line).",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        help="Base directory for relative paths in --list-file.",
    )
    parser.add_argument(
        "--mode",
        choices=["parse-cst", "parse-model", "roundtrip"],
        default="roundtrip",
        help="Which pipeline stages to execute (default: roundtrip).",
    )
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--count-nodes",
        action="store_true",
        help="Count tree-sitter nodes (adds overhead).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files processed.",
    )
    args = parser.parse_args()

    paths = iter_paths(args.paths, args.list_file, args.base_dir)
    if args.limit is not None:
        paths = paths[: args.limit]
    if not paths:
        print("No input files found.", file=os.sys.stderr)
        return 2

    for _ in range(args.warmup):
        for path in paths:
            run_once(path, args.mode, include_counts=False)

    for iteration in range(args.iterations):
        for path in paths:
            result = run_once(path, args.mode, include_counts=args.count_nodes)
            result["iteration"] = iteration
            result["mode"] = args.mode
            print(json.dumps(result, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
