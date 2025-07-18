from __future__ import annotations

import re
from typing import Any, ClassVar, List, Optional, Union

from tree_sitter import Node

from nix_manipulator.expressions import Comment, empty_line, linebreak
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.format import _format_trivia


def process_list(node: Node):
    from nix_manipulator.mapping import tree_sitter_node_to_expression

    before: list[Any] = []

    def push_gap(prev: Optional[Node], cur: Node) -> None:
        """Detect an empty line between *prev* and *cur*."""
        if prev is None:
            return
        start = prev.end_byte - node.start_byte
        end = cur.start_byte - node.start_byte
        gap = node.text[start:end].decode()
        if re.search(r"\n[ \t]*\n", gap):
            before.append(empty_line)
        elif "\n" in gap:  # exactly one line-break — keep it
            before.append(linebreak)

    prev_content: Optional[Node] = None
    values: list = []
    for child in node.children:
        if child.type in ("[", "]"):
            continue
        push_gap(prev_content, child)
        child_expression: NixExpression = tree_sitter_node_to_expression(child)
        if isinstance(child_expression, Comment):
            before.append(child_expression)
        else:
            child_expression.before = before
            values.append(child_expression)
            before = []

        prev_content = child

    if before:
        values[-1].after.extend(before)
    return values


class NixList(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"list_expression"}
    value: List[Union[NixExpression, str, int, bool]]
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("List has no code")

        multiline = b"\n" in node.text
        value = list(process_list(node))

        return cls(value=value, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct list."""
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)
        indented = indent + 2 if self.multiline else indent
        indentation = "" if inline else " " * indented

        if not self.value:
            return f"{before_str}[ ]{after_str}"

        items = []
        for item in self.value:
            if isinstance(item, Primitive):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, Identifier):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, NixExpression):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, str):
                items.append(f'{indentation}"{item}"')
            elif isinstance(item, bool):
                items.append(f"{indentation}{'true' if item else 'false'}")
            elif isinstance(item, int):
                items.append(f"{indentation}{item}")
            else:
                raise ValueError(f"Unsupported list item type: {type(item)}")

        if self.multiline:
            # Add proper indentation for multiline lists
            items_str = "\n".join(items)
            indentor = "" if inline else (" " * indent)
            return (
                f"{before_str}"
                + indentor
                + f"[\n{items_str}\n"
                + " " * indent
                + f"]{after_str}"
            )
        else:
            items_str = " ".join(items)
            return f"{before_str}[ {items_str} ]{after_str}"

    def __repr__(self):
        return f"NixList(\nvalue={self.value}\n)"


__all__ = ["NixList"]
