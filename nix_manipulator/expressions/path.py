from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression

_SOURCE_PATH: ContextVar[Path | None] = ContextVar("nix_source_path", default=None)


@contextmanager
def source_path_context(path: Path | None):
    """Attach a base path so Nix paths can resolve file content."""
    token = _SOURCE_PATH.set(path)
    try:
        yield
    finally:
        _SOURCE_PATH.reset(token)


@dataclass(slots=True, repr=False)
class NixPath(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {
        "path_expression",
        "spath_expression",
        "hpath_expression",
    }
    path: str
    source_path: Path | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ):
        """Capture raw path text to keep Nix path semantics intact."""
        if node.text is None:
            raise ValueError("Path is missing")
        path = node.text.decode()
        source_path = _SOURCE_PATH.get()
        return cls(
            path=path,
            source_path=source_path,
            before=before or [],
            after=after or [],
        )

    @property
    def value(self) -> bytes:
        """Read the path target as bytes, resolving relative to the source file."""
        return self.resolved_path().read_bytes()

    @property
    def text(self) -> str:
        """Read the path target as UTF-8 text."""
        return self.resolved_path().read_text(encoding="utf-8")

    def resolved_path(self) -> Path:
        """Resolve the path literal to a filesystem path."""
        if self.path.startswith("<") and self.path.endswith(">"):
            raise ValueError("Angle-bracket paths require NIX_PATH resolution")
        resolved = Path(self.path)
        if not resolved.is_absolute() and self.source_path is not None:
            resolved = self.source_path.parent / resolved
        return resolved

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        return self.add_trivia(self.path, indent, inline)


__all__ = ["NixPath"]
