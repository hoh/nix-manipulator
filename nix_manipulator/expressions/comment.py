from __future__ import annotations

from typing import ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression


class Comment(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"comment"}
    text: str

    def __str__(self):
        lines = self.text.split("\n")
        return "\n".join(f"# {line}" for line in lines)

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing comment")
        text = node.text.decode()
        if text.startswith("#"):
            text = text[1:]
            if text.startswith(" "):
                text = text[1:]
        return cls(text=text)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        return " " * indent + str(self)


class MultilineComment(Comment):
    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        if "\n" in self.text:
            # Multiline
            result: str
            if self.text.startswith("\n"):
                result = " " * indent + "/*"
            else:
                result = "/* "

            result += self.text.replace("\n", "\n" + " " * indent)

            if not self.text.endswith("\n"):
                result += " */"
            else:
                result += "*/"
            return result
        else:
            # Single line
            return f"/* {self.text} */"


__all__ = ["Comment", "MultilineComment"]
