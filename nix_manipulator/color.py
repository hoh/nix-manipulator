from __future__ import annotations

import os
import sys

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import NixLexer


def colorize_nix(code: str) -> str:
    """Highlight Nix snippets when pygments is available."""
    if (not code) or (os.getenv("NO_COLOR") == "1") or (not sys.stdout.isatty()):
        return code
    return highlight(code, NixLexer(), TerminalFormatter())


__all__ = ["colorize_nix"]
