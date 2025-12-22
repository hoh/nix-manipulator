from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


@dataclass(slots=True)
class Comment(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"comment"}
    text: str
    inline: bool = False
    shebang: bool = False
    space_after_hash: bool = True

    def __str__(self):
        """Render comment text to preserve stylistic intent across rebuilds."""
        if self.shebang:
            return f"#!{self.text}"
        prefix = "# " if self.space_after_hash else "#"
        lines = self.text.split("\n")
        rendered = []
        for line in lines:
            rendered.append(f"{prefix}{line}" if line else "#")
        return "\n".join(rendered)

    @classmethod
    def from_cst(cls, node: Node):
        """Normalize comment syntax so formatting rules stay consistent."""
        if node.text is None:
            raise ValueError("Missing comment")
        text = node.text.decode()
        if text.startswith("/*"):
            doc = text.startswith("/**")
            opener_len = 3 if doc else 2
            inner = text[opener_len:]
            if inner.endswith("*/"):
                inner = inner[:-2]
            if "\n" in inner:
                indent_prefix = " " * node.start_point.column
                lines = inner.split("\n")
                normalized = [lines[0]]
                for line in lines[1:]:
                    if indent_prefix and line.startswith(indent_prefix):
                        line = line[len(indent_prefix) :]
                    normalized.append(line)
                inner_indent = None
                for line in normalized[1:]:
                    if not line.strip():
                        continue
                    leading = len(line) - len(line.lstrip(" "))
                    inner_indent = leading if inner_indent is None else min(
                        inner_indent, leading
                    )
                if inner_indent is None:
                    inner_indent = 0
                if inner_indent:
                    trimmed = [normalized[0]]
                    for line in normalized[1:]:
                        if line.startswith(" " * inner_indent):
                            line = line[inner_indent:]
                        trimmed.append(line)
                    inner = "\n".join(trimmed)
                else:
                    inner = "\n".join(normalized)
                return MultilineComment(
                    text=inner, doc=doc, inner_indent=inner_indent
                )
            inner = inner.strip()
            return MultilineComment(text=inner, doc=doc)
        if text.startswith("#!"):
            return cls(text=text[2:], shebang=True)
        if text.startswith("#"):
            space_after_hash = False
            text = text[1:]
            if text.startswith(" "):
                space_after_hash = True
                text = text[1:]
            return cls(text=text, space_after_hash=space_after_hash)
        return cls(text=text)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Keep indentation stable so comments stay attached to their targets."""
        if self.inline:
            indent = 0
        return " " * indent + str(self)


@dataclass(slots=True)
class MultilineComment(Comment):
    doc: bool = False
    inner_indent: int | None = None

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Preserve multiline comment structure for RFC-166 compliance."""
        opening = "/**" if self.doc else "/*"
        if "\n" in self.text:
            # Multiline
            result: str
            if self.text.startswith("\n"):
                result = " " * indent + opening
            else:
                result = f"{opening} "
            lines = self.text.split("\n")
            result += lines[0]
            extra_indent = 2 if self.inner_indent is None else self.inner_indent
            for line in lines[1:]:
                if line:
                    result += "\n" + " " * (indent + extra_indent) + line
                else:
                    result += "\n"

            if not self.text.endswith("\n"):
                result += " */"
            else:
                result += " " * indent + "*/"
            return result
        else:
            # Single line
            return f"{opening} {self.text} */"


__all__ = ["Comment", "MultilineComment"]
