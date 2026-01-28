"""Function calls with preserved trivia between name and arguments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.trivia import (
    collect_comments_between_with_gap, gap_between, layout_from_gap,
    trim_leading_layout_trivia)


@dataclass(slots=True, repr=False)
class FunctionCall(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"apply_expression"}
    name: NixExpression | str
    argument: NixExpression | None = None
    recursive: bool = False
    argument_gap: str | None = None
    function_after: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize string inputs to expressions for uniform formatting."""
        NixExpression.__post_init__(self)
        if isinstance(self.name, str):
            self.name = Identifier(name=self.name)
        if self.argument is not None and isinstance(
            self.argument, (str, int, bool, float)
        ):
            from nix_manipulator.expressions.expression import \
                coerce_expression

            self.argument = coerce_expression(self.argument)

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ):
        """Capture spacing around function/argument to preserve call style."""
        if node.text is None or node.text == b"":
            raise ValueError("Missing function name")

        function_node = node.child_by_field_name("function")
        argument_node = node.child_by_field_name("argument")
        if function_node is None or argument_node is None:
            raise ValueError("Missing function name")
        if function_node.text is None:
            raise ValueError("Missing function name")

        recursive = argument_node.type == "rec_attrset_expression"

        from nix_manipulator.mapping import tree_sitter_node_to_expression

        name = tree_sitter_node_to_expression(function_node)
        argument = tree_sitter_node_to_expression(argument_node)

        before_argument: list[Any] = []
        function_after: list[Any] = []
        comment_nodes = [
            child
            for child in node.children
            if child.type == "comment"
            and function_node.end_byte <= child.start_byte < argument_node.start_byte
        ]
        inline_comment_nodes = [
            child
            for child in comment_nodes
            if child.start_byte > function_node.end_byte
            and child.start_point.row == function_node.end_point.row
        ]
        if inline_comment_nodes:
            inline_comment_nodes.sort(key=lambda child: child.start_byte)
            for comment_node in inline_comment_nodes:
                comment_expr = Comment.from_cst(comment_node)
                comment_expr.inline = True
                function_after.append(comment_expr)
        comment_nodes = [
            child for child in comment_nodes if child not in inline_comment_nodes
        ]
        if comment_nodes:
            comment_trivia, _ = collect_comments_between_with_gap(
                node,
                comment_nodes,
                function_node,
                argument_node,
                allow_inline=False,
            )
            before_argument.extend(comment_trivia)

        gap = gap_between(node, function_node, argument_node)
        argument_gap = gap

        if before_argument:
            argument.before = before_argument + argument.before

        return cls(
            name=name,
            argument=argument,
            recursive=recursive,
            argument_gap=argument_gap,
            function_after=function_after,
            before=before or [],
            after=after or [],
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function call."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        name_expr = self.name
        if isinstance(name_expr, str):
            name_expr = Identifier(name=name_expr)

        function_str = name_expr.rebuild(indent=indent, inline=True)
        if self.function_after:
            for item in self.function_after:
                if isinstance(item, Comment) and item.inline:
                    if not function_str.endswith(" "):
                        function_str += " "
                    function_str += item.rebuild(indent=0)
                else:
                    if not function_str.endswith("\n"):
                        function_str += "\n"
                    function_str += item.rebuild(indent=indent)

        if not self.argument:
            return self.add_trivia(function_str, indent, inline)

        argument_expr = self.argument
        if self.argument_gap is None:
            preview = argument_expr.rebuild(indent=indent, inline=True)
            prefer_newline = not inline and indent > 0 and "\n" in preview
            arg_indent = indent if prefer_newline else indent
            if prefer_newline:
                trimmed_before = trim_leading_layout_trivia(argument_expr.before)
                if trimmed_before != argument_expr.before:
                    argument_expr = argument_expr.model_copy(
                        update={"before": trimmed_before}
                    )
            args_str = argument_expr.rebuild(
                indent=arg_indent, inline=not prefer_newline
            )
            if prefer_newline and args_str and not args_str[0].isspace():
                args_str = (" " * arg_indent) + args_str
            sep = "\n" if prefer_newline else " "
        else:
            argument_layout = layout_from_gap(self.argument_gap)
            arg_indent = (
                argument_layout.indent
                if argument_layout.on_newline
                and argument_layout.indent is not None
                else (indent + 2 if argument_layout.on_newline else indent)
            )
            if argument_layout.on_newline:
                trimmed_before = trim_leading_layout_trivia(argument_expr.before)
                if trimmed_before != argument_expr.before:
                    argument_expr = argument_expr.model_copy(
                        update={"before": trimmed_before}
                    )
            args_str = argument_expr.rebuild(
                indent=arg_indent, inline=not argument_layout.on_newline
            )
            if argument_layout.on_newline and args_str and not args_str[0].isspace():
                args_str = (" " * arg_indent) + args_str
            sep = (
                "\n\n"
                if argument_layout.blank_line
                else ("\n" if argument_layout.on_newline else " ")
            )

        rec_str = ""
        if self.recursive:
            if not isinstance(self.argument, AttributeSet) or not self.argument.recursive:
                rec_str = " rec"

        core = f"{function_str}{rec_str}{sep}{args_str}"
        return self.add_trivia(core, indent, inline)


__all__ = ["FunctionCall"]
