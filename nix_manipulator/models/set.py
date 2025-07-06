from __future__ import annotations

import re
from typing import List, Dict, Any, Optional

from tree_sitter import Node

from nix_manipulator.format import _format_trivia
from nix_manipulator.models.expression import NixExpression
from nix_manipulator.models.comment import Comment
from nix_manipulator.models.function.call import FunctionCall
from nix_manipulator.models.inherit import NixInherit
from nix_manipulator.models.layout import empty_line, linebreak


class NixAttributeSet(NixExpression):
    values: List[NixBinding | NixInherit | FunctionCall]
    multiline: bool = True
    recursive: bool = False

    @classmethod
    def from_dict(cls, values: Dict[str, NixExpression]):
        from nix_manipulator.models.binding import NixBinding
        values_list = []
        for key, value in values.items():
            values_list.append(NixBinding(name=key, value=value))
        return cls(values=values_list)

    @classmethod
    def from_cst(cls, node: Node) -> NixAttributeSet:
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
        from nix_manipulator.models.binding import NixBinding
        multiline = b"\n" in node.text
        values: list[NixBinding | NixInherit] = []
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

        # Flatten content: unwrap `binding_set` if present
        content_nodes: list[Node] = []
        for child in node.named_children:
            if child.type == "binding_set":
                content_nodes.extend(child.named_children)
            else:
                content_nodes.append(child)

        prev_content: Optional[Node] = None
        for child in content_nodes:
            if child.type in (
                "binding",
                "comment",
                "variable_expression",
                "inherit",
                "string_fragment",
            ):
                push_gap(prev_content, child)

                if child.type == "binding":
                    values.append(NixBinding.from_cst(child, before=before))
                    before = []
                elif child.type == "comment":
                    comment = Comment.from_cst(child)
                    # Inline only when comment shares the *same row* as the binding terminator
                    inline_to_prev = (
                        prev_content is not None
                        and prev_content.type == "binding"
                        and child.start_point.row == prev_content.end_point.row
                        and values
                    )
                    if inline_to_prev:
                        values[-1].after.append(
                            comment
                        )  # attach to the *after*-trivia of that binding
                    else:
                        before.append(comment)
                elif child.type == "inherit":
                    values.append(NixInherit.from_cst(child, before=before))
                    before = []
                elif child.type == "variable_expression":
                    # variable_expression – a function call
                    values.append(FunctionCall.from_cst(child, before=before))
                    before = []
                elif child.type == "string_fragment":
                    # Used by the function call called with the previous child
                    pass
                else:
                    raise ValueError(f"Unsupported child node: {child} {child.type}")

                prev_content = child
            else:
                raise ValueError(f"Unsupported attrset child: {child.type}")

        # Attach dangling trivia to the last binding
        if before and values:
            values[-1].after.extend(before)

        return cls(values=values, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2
        before_str = _format_trivia(self.before, indent=indented)
        after_str = _format_trivia(self.after, indent=indented)

        if not self.values:
            return f"{before_str}{{ }}{after_str}"

        if self.multiline:
            bindings_str = "\n".join(
                [value.rebuild(indent=indented, inline=False) for value in self.values]
            )
            return (
                f"{before_str}{{"
                + f"\n{bindings_str}\n"
                + " " * indent
                + f"}}{after_str}"
            )
        else:
            bindings_str = " ".join(
                [value.rebuild(indent=indented, inline=True) for value in self.values]
            )
            return f"{before_str}{{ {bindings_str} }}{after_str}"


class RecursiveAttributeSet(NixAttributeSet):
    values: List[NixBinding | NixInherit | FunctionCall]
    multiline: bool = True
    recursive: bool = True
