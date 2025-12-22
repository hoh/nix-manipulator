from __future__ import annotations


class EmptyLine:
    def __repr__(self):
        """Render a stable sentinel name for debugging layout markers."""
        return "EmptyLine"


class Linebreak:
    def __repr__(self):
        """Render a stable sentinel name for debugging layout markers."""
        return "Linebreak"


class Comma:
    def __repr__(self):
        """Render a stable sentinel name for debugging layout markers."""
        return "Comma"


empty_line = EmptyLine()
linebreak = Linebreak()
comma = Comma()


__all__ = ["empty_line", "linebreak", "comma"]
