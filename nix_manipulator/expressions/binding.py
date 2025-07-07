from __future__ import annotations

import json
import re
from typing import Any, List, Union

from tree_sitter import Node

from nix_manipulator.expressions.binary import NixBinaryExpression
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.identifier import NixIdentifier
from nix_manipulator.expressions.layout import linebreak
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.select import NixSelect
from nix_manipulator.expressions.with_statement import NixWith
from nix_manipulator.format import _format_trivia


class NixBinding(NixExpression):
    name: str
    value: Union[NixExpression, str, int, bool]
    newline_after_equals: bool = False

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        before = before or []
        after = after or []

        children = (
            node.children[0].children if len(node.children) == 1 else node.children
        )

        name: str | None = None
        value: Any | None = None

        from nix_manipulator.expressions.set import NixAttributeSet

        for child in children:
            if child.type in ("=", ";"):
                continue
            elif child.type in "attrpath":
                name = child.text.decode()
            elif child.type == "string_expression":
                value = Primitive(value=json.loads(child.text.decode()))
            elif child.type == "integer_expression":
                value = Primitive(value=int(child.text.decode()))
            elif child.type == "list_expression":
                value = NixList.from_cst(child)
            elif child.type == "binary_expression":
                value = NixBinaryExpression.from_cst(child)
            elif child.type == "variable_expression":
                value = NixIdentifier.from_cst(child)
            elif child.type == "attrset_expression":
                value = NixAttributeSet.from_cst(child)
            elif child.type == "apply_expression":
                value = FunctionCall.from_cst(child)
            elif child.type == "select_expression":
                value = NixSelect.from_cst(child)
            elif child.type == "with_expression":
                value = NixWith.from_cst(child)
            else:
                raise ValueError(f"Unsupported child node: {child} {child.type}")

        if name is None or value is None:
            raise ValueError("Could not parse binding")

        newline_after_equals = bool(re.search(r"=\s*\n", node.text.decode()))

        return cls(
            name=name,
            value=value,
            before=before,
            after=after,
            newline_after_equals=newline_after_equals,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:  # noqa: C901
        """Reconstruct binding, preserving possible newline after '='."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent

        # Decide how the *value* itself has to be rendered
        val_indent = indent + 2 if self.newline_after_equals else indent

        if isinstance(self.value, NixExpression):
            value_str = self.value.rebuild(
                indent=val_indent, inline=not self.newline_after_equals
            )
        elif isinstance(self.value, str):
            value_str = (
                " " * val_indent if self.newline_after_equals else ""
            ) + f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = (" " * val_indent if self.newline_after_equals else "") + (
                "true" if self.value else "false"
            )
        elif isinstance(self.value, int):
            value_str = (" " * val_indent if self.newline_after_equals else "") + str(
                self.value
            )
        else:
            raise ValueError(f"Unsupported value type: {type(self.value)}")

        # Assemble left-hand side
        head = f"{indentation}{self.name} ="
        sep = "\n" if self.newline_after_equals else " "
        core = f"{head}{sep}{value_str};"

        if self.after and isinstance(self.after[0], Comment):
            inline_comment = self.after[0].rebuild(indent=0)
            trailing = _format_trivia(self.after[1:], indent=indent)
            return f"{before_str}{core} {inline_comment}{trailing}"

        if self.after and self.after[0] is linebreak:
            trailing = _format_trivia(self.after[1:], indent=indent)
            if not trailing.startswith("\n"):
                trailing = "\n" + trailing
            if trailing.endswith("\n"):
                trailing = trailing[:-1]
            return f"{before_str}{core}{trailing}"

        if self.after and self.after[-1] is not linebreak and after_str.endswith("\n"):
            after_str = after_str[:-1]

        return f"{before_str}{core}" + (f"\n{after_str}" if after_str else "")


__all__ = ["NixBinding"]
