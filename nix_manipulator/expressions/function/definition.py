from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Union

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import empty_line
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.format import _format_trivia


class FunctionDefinition(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"function_expression"}
    argument_set: Identifier | List[Identifier | Ellipses] = []
    argument_set_is_multiline: bool = True
    breaks_after_semicolon: Optional[int] = None
    output: Union[AttributeSet, NixExpression, None] = None

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Function definition has no code")

        children_types = [child.type for child in node.children]
        assert children_types in (
            ["formals", ":", "attrset_expression"],
            ["formals", ":", "apply_expression"],
            ["formals", ":", "let_expression"],
            ["identifier", ":", "attrset_expression"],
            ["identifier", ":", "with_expression"],
            ["formals", ":", "function_expression"],
            ["formals", ":", "variable_expression"],
        ), (
            f"Output other than attrset_expression not supported yet. You used {children_types}"
        )

        argument_set = []
        if node.children[0].type == "formals":
            argument_set_is_multiline = (
                b"\n" in node.child_by_field_name("formals").text
            )

            before = []
            previous_child = node.child_by_field_name("formals").children[0]
            assert previous_child.type == "{"
            for child in node.child_by_field_name("formals").children:
                if child.type in ("{", "}"):
                    continue
                elif child.type == ",":
                    # Don't continue, we want to have it as previous_child
                    pass
                elif child.type == "formal":
                    children = iter(child.children)
                    for grandchild in children:
                        if grandchild.type == "identifier":
                            if grandchild.text == b"":
                                # Trailing commas add a "MISSING identifier" element with body b""
                                continue

                            if previous_child:
                                gap = node.text[
                                    previous_child.end_byte : child.start_byte
                                ].decode()
                                is_empty_line = False
                                if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                                    before.append(empty_line)
                                    is_empty_line = True

                            argument_set.append(
                                Identifier.from_cst(grandchild, before=before)
                            )
                            before = []
                        elif grandchild.type == "?":
                            from nix_manipulator.mapping import (
                                tree_sitter_node_to_expression,
                            )

                            default_value_node = children.__next__()
                            default_value = tree_sitter_node_to_expression(
                                default_value_node
                            )
                            # Update in place
                            identifier: Identifier = argument_set[-1]
                            identifier.default_value = default_value
                        else:
                            raise ValueError(
                                f"Unsupported child node: {grandchild} {grandchild.type}"
                            )
                elif child.type == "ellipses":
                    # argument_set.append(Primitive.from_cst(child, before=before))
                    argument_set.append(Ellipses.from_cst(child))
                elif child.type == "comment":
                    if previous_child:
                        gap = node.text[
                            previous_child.end_byte : child.start_byte
                        ].decode()
                        is_empty_line = False
                        if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                            before.append(empty_line)
                            is_empty_line = True

                    before.append(Comment.from_cst(child))
                elif child.type == "ERROR" and child.text == b",":
                    # Trailing commas are RFC compliant but add a 'ERROR' element..."
                    pass
                else:
                    raise ValueError(f"Unsupported child node: {child} {child.type}")
                previous_child = child

            if before:
                # No binding followed the comment so it could not be attached to it
                argument_set[-1].after += before

        else:
            assert node.children[0].type == "identifier"
            argument_set = Identifier.from_cst(node.children[0])
            argument_set_is_multiline = False

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        body: Node = node.child_by_field_name("body")
        if body.type in (
            "attrset_expression",
            "apply_expression",
            "let_expression",
            "with_expression",
            "function_expression",
            "variable_expression",
        ):
            output: NixExpression = tree_sitter_node_to_expression(body)
        else:
            raise ValueError(f"Unsupported output node: {body} {body.type}")

        def get_semicolon_index(text) -> int:
            for child in node.children:
                if child.type == ":":
                    return child.end_byte
            return -1

        after_semicolon: bytes = node.text[
            get_semicolon_index(node) : node.child_by_field_name("body").start_byte
        ]
        breaks_after_semicolon: int = after_semicolon.count(
            b"\n"
        )  # or let_statements...

        return cls(
            breaks_after_semicolon=breaks_after_semicolon,
            argument_set=argument_set,
            output=output,
            argument_set_is_multiline=argument_set_is_multiline,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function definition."""
        indent += 2
        before_str = _format_trivia(self.before, indent=indent)
        after_str = _format_trivia(self.after, indent=indent)

        # Build argument set
        if not self.argument_set:
            args_str = "{ }"
        elif isinstance(self.argument_set, Identifier):
            args_str = self.argument_set.rebuild(
                indent=indent, inline=not self.argument_set_is_multiline
            )
        else:
            args = []
            indentation = " " * indent if self.argument_set_is_multiline else ""
            for i, arg in enumerate(self.argument_set):
                is_last_argument: bool = i == len(self.argument_set) - 1
                args.append(
                    arg.rebuild(
                        indent=indent,
                        inline=not self.argument_set_is_multiline,
                        trailing_comma=self.argument_set_is_multiline,
                    )
                )

            if self.argument_set_is_multiline:
                args_str = "{\n" + "\n".join(args) + "\n}"
            else:
                args_str = "{ " + ", ".join(args) + " }"

        # Build result)
        output_str = self.output.rebuild() if self.output else "{ }"

        breaks_after_semicolon: int
        if self.breaks_after_semicolon is not None:
            breaks_after_semicolon = self.breaks_after_semicolon
        elif isinstance(self.output, LetExpression):
            breaks_after_semicolon = 1
        else:
            breaks_after_semicolon = (
                1
                if isinstance(self.output, LetExpression)
                or (self.argument_set_is_multiline and len(self.argument_set) > 0)
                else 0
            )
        line_break = "\n" * breaks_after_semicolon

        # Format the final string - use single line format when no arguments and no let statements
        if (not self.argument_set) and (not isinstance(self.output, LetExpression)):
            split = ": " if not line_break else ":" + line_break
            return f"{before_str}{args_str}{split}{output_str}{after_str}"
        else:
            split = ": " if not line_break else ":" + line_break
            return f"{before_str}{args_str}{split}{output_str}{after_str}"


__all__ = ["FunctionDefinition"]
