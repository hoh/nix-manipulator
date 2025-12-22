"""Function definitions with whitespace-aware argument parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterator, cast

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import comma, empty_line, linebreak
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.trivia import (
    apply_trailing_trivia, collect_comment_trivia_between,
    format_interstitial_trivia_with_separator, format_trivia, gap_between,
    gap_from_offsets, layout_from_gap)


def _parse_named_argument_set(node: Node) -> tuple[Identifier | None, bool]:
    """Parse named argument set metadata for function signatures."""
    signature_nodes = [child for child in node.children if child.type != "comment"]
    children_types = [child.type for child in signature_nodes]

    if len(children_types) < 2:
        raise ValueError(
            f"Function definition is missing expected tokens: {children_types}"
        )
    supports_named_args = len(children_types) > 1 and children_types[1] == "@"
    if not (
        children_types[:2] in (["formals", ":"], ["identifier", ":"])
        or supports_named_args
    ):
        raise ValueError(
            f"Unsupported function definition signature: {children_types}"
        )

    if supports_named_args:
        if len(children_types) < 3:
            raise ValueError(
                f"Named argument set is incomplete: {children_types}"
            )
        if children_types[0] == "identifier":
            if children_types[2] != "formals":
                raise ValueError(
                    f"Expected formals after named arg set: {children_types}"
                )
            named_attribute_set = Identifier.from_cst(signature_nodes[0])
            named_attribute_set_before_formals = True
        else:
            if children_types[0] != "formals" or children_types[2] != "identifier":
                raise ValueError(
                    f"Expected formals@identifier syntax: {children_types}"
                )
            named_attribute_set = Identifier.from_cst(signature_nodes[2])
            named_attribute_set_before_formals = False
        return named_attribute_set, named_attribute_set_before_formals

    return None, False


def _parse_formal_default(
    node: Node,
    children: Iterator[Node],
    question_node: Node,
    identifier: Identifier,
) -> None:
    """Parse a default value for a formal and attach trivia."""
    from nix_manipulator.mapping import tree_sitter_node_to_expression

    default_before: list[Any] = []
    default_inline_comments: list[Comment] = []
    prev_default = question_node
    default_value_node: Node | None = None
    while True:
        try:
            default_value_node = next(children)
        except StopIteration:
            raise ValueError("Function definition default value is missing") from None
        if default_value_node.type == "comment":
            gap = gap_between(node, prev_default, default_value_node)
            comment = Comment.from_cst(default_value_node)
            inline_comment = (
                default_value_node.start_point.row
                == question_node.start_point.row
            )
            if inline_comment:
                comment.inline = True
                default_inline_comments.append(comment)
            else:
                if re.search(r"\n[ \t]*\n", gap):
                    default_before.append(empty_line)
                default_before.append(comment)
            prev_default = default_value_node
            continue
        break

    gap = gap_between(node, prev_default, default_value_node)
    gap_newlines = gap.count("\n")
    if gap_newlines > 1:
        default_before.extend([empty_line] * (gap_newlines - 1))
    default_value = tree_sitter_node_to_expression(default_value_node)
    if default_before:
        default_value.before = default_before + default_value.before
    identifier.default_value = default_value
    gap = gap_between(node, question_node, default_value_node)
    identifier.default_value_on_newline = "\n" in gap
    if identifier.default_value_on_newline:
        identifier.default_value_indent = default_value_node.start_point.column
    if default_inline_comments:
        identifier.after_question.extend(default_inline_comments)


def _parse_argument_set(
    node: Node,
) -> tuple[
    Identifier | list[Identifier | Ellipses],
    bool | None,
    int,
    list[Any],
    int | None,
]:
    """Parse formals/identifier argument sets with trivia retention."""
    argument_set_trailing_empty_lines = 0
    argument_set_inner_trivia: list[Any] = []
    argument_set_trailing_comment_indent: int | None = None
    formals_node = node.child_by_field_name("formals")
    if formals_node is not None:
        if formals_node.text is None:
            raise ValueError("Function definition has no formals text")
        argument_set_is_multiline = b"\n" in formals_node.text

        argument_set: list[Identifier | Ellipses] = []
        before: list[Any] = []
        pending_comment_indent: int | None = None
        pending_comma_node: Node | None = None
        pending_comma_empty_line = False

        def flush_pending_comma(next_node: Node) -> None:
            """Carry trailing comma trivia so argument lists keep spacing."""
            nonlocal pending_comma_node, pending_comma_empty_line, before
            assert pending_comma_node is not None
            gap = gap_between(node, pending_comma_node, next_node)
            if "\n" in gap:
                if pending_comma_empty_line:
                    before.append(empty_line)
                before.append(comma)
                before.append(linebreak)
            pending_comma_node = None
            pending_comma_empty_line = False

        if not formals_node.children:
            raise ValueError("Function definition formals are empty")
        previous_child = formals_node.children[0]
        if previous_child.type != "{":
            raise ValueError(
                "Function definition formals are missing an opening brace"
            )
        for child in formals_node.children:
            if child.type in ("{", "}"):
                continue
            elif child.type == ",":
                pending_comma_node = None
                pending_comma_empty_line = False
                if previous_child:
                    gap = gap_between(node, previous_child, child)
                    if "\n" in gap:
                        pending_comma_node = child
                        pending_comma_empty_line = bool(
                            re.match(r"[ ]*\n[ ]*\n[ ]*", gap)
                        )
                previous_child = child
                continue
            elif child.type == "formal":
                if pending_comma_node is not None:
                    flush_pending_comma(child)
                children = iter(child.children)
                for grandchild in children:
                    if grandchild.type == "identifier":
                        if grandchild.text == b"":
                            # Trailing commas add a "MISSING identifier" element with body b""
                            continue

                        if previous_child:
                            gap = gap_between(node, previous_child, child)
                            if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                                before.append(empty_line)

                        argument_set.append(
                            Identifier.from_cst(grandchild, before=before)
                        )
                        before = []
                        pending_comment_indent = None
                    elif grandchild.type == "?":
                        identifier = cast(Identifier, argument_set[-1])
                        _parse_formal_default(
                            node,
                            children,
                            grandchild,
                            identifier,
                        )
                    else:
                        raise ValueError(
                            f"Unsupported child node: {grandchild} {grandchild.type}"
                        )
            elif child.type == "ellipses":
                if pending_comma_node is not None:
                    flush_pending_comma(child)
                if previous_child:
                    gap = gap_between(node, previous_child, child)
                    if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                        before.append(empty_line)
                ellipses = Ellipses.from_cst(child)
                ellipses.before = before
                argument_set.append(ellipses)
                before = []
                pending_comment_indent = None
            elif child.type == "comment":
                if pending_comma_node is not None and (
                    child.start_point.row == pending_comma_node.start_point.row
                ):
                    if pending_comma_empty_line:
                        before.append(empty_line)
                    before.append(comma)
                    comment = Comment.from_cst(child)
                    comment.inline = True
                    before.append(comment)
                    pending_comma_node = None
                    pending_comma_empty_line = False
                    previous_child = child
                    continue
                if pending_comma_node is not None:
                    flush_pending_comma(child)
                if previous_child:
                    gap = gap_between(node, previous_child, child)
                    if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                        before.append(empty_line)
                comment = Comment.from_cst(child)
                inline_to_prev = (
                    previous_child is not None
                    and child.start_point.row == previous_child.end_point.row
                    and argument_set
                )
                if inline_to_prev:
                    comment.inline = True
                    argument_set[-1].after.append(comment)
                else:
                    before.append(comment)
                    if pending_comment_indent is None:
                        pending_comment_indent = child.start_point.column
            elif child.type == "ERROR" and child.text == b",":
                # Trailing commas are RFC compliant but add a 'ERROR' element..."
                pass
            else:
                raise ValueError(f"Unsupported child node: {child} {child.type}")
            previous_child = child

        closing_brace = next(
            (child for child in formals_node.children if child.type == "}"),
            None,
        )
        if closing_brace is not None and previous_child is not None:
            gap = gap_between(node, previous_child, closing_brace)
            gap_newlines = gap.count("\n")
            if gap_newlines > 1:
                argument_set_trailing_empty_lines = gap_newlines - 1
        if before:
            # Preserve dangling trivia even when formals are empty.
            if argument_set:
                argument_set[-1].after += before
                argument_set_trailing_comment_indent = pending_comment_indent
            else:
                argument_set_inner_trivia = before

        return (
            argument_set,
            argument_set_is_multiline,
            argument_set_trailing_empty_lines,
            argument_set_inner_trivia,
            argument_set_trailing_comment_indent,
        )

    if not node.children or node.children[0].type != "identifier":
        raise ValueError("Function definition is missing its identifier")

    return Identifier.from_cst(node.children[0]), False, 0, [], None


def _parse_function_signature(
    node: Node,
) -> tuple[
    Identifier | None,
    bool,
    Identifier | list[Identifier | Ellipses],
    bool | None,
    int,
    list[Any],
    int | None,
]:
    """Parse the function signature into named args and formals metadata."""
    named_attribute_set, named_attribute_set_before_formals = (
        _parse_named_argument_set(node)
    )
    (
        argument_set,
        argument_set_is_multiline,
        argument_set_trailing_empty_lines,
        argument_set_inner_trivia,
        argument_set_trailing_comment_indent,
    ) = _parse_argument_set(node)
    return (
        named_attribute_set,
        named_attribute_set_before_formals,
        argument_set,
        argument_set_is_multiline,
        argument_set_trailing_empty_lines,
        argument_set_inner_trivia,
        argument_set_trailing_comment_indent,
    )


def _parse_function_body(node: Node) -> tuple[Node, NixExpression]:
    """Parse the function body node and expression."""
    from nix_manipulator.mapping import tree_sitter_node_to_expression

    body_node = node.child_by_field_name("body")
    if body_node is None:
        raise ValueError("Function definition has no body")
    return body_node, tree_sitter_node_to_expression(body_node)


def _apply_before_body_trivia(
    output: NixExpression,
    trivia: list[Any],
) -> None:
    """Attach trivia captured between the colon and body."""
    if trivia:
        output.before = trivia + output.before


def _collect_colon_trivia(
    node: Node,
    body_node: Node,
) -> tuple[list[Any], str, Comment | None, int, list[Any]]:
    """Capture colon-adjacent trivia for function definitions."""
    colon_node = next((child for child in node.children if child.type == ":"), None)
    before_colon_comments: list[Any] = []
    before_colon_gap = ""
    after_colon_comment: Comment | None = None
    breaks_after_semicolon = 0
    before_body_trivia: list[Any] = []

    if colon_node is None:
        return (
            before_colon_comments,
            before_colon_gap,
            after_colon_comment,
            breaks_after_semicolon,
            before_body_trivia,
        )

    args_end_node: Node | None = None
    for child in node.children:
        if child == colon_node:
            break
        if child.type != "comment":
            args_end_node = child
    if args_end_node is not None:
        comment_nodes = [
            child
            for child in node.children
            if child.type == "comment"
            and args_end_node.end_byte <= child.start_byte < colon_node.start_byte
        ]
        if comment_nodes:
            before_colon_comments = collect_comment_trivia_between(
                node,
                comment_nodes,
                args_end_node,
                colon_node,
                allow_inline=True,
            )
            comment_nodes.sort(key=lambda child: child.start_byte)
            before_colon_gap = gap_between(node, comment_nodes[-1], colon_node)
        else:
            before_colon_gap = gap_between(node, args_end_node, colon_node)

    inline_comment_node: Node | None = None
    between_comment_nodes: list[Node] = []
    for child in node.children:
        if child.type != "comment":
            continue
        if not (colon_node.end_byte <= child.start_byte < body_node.start_byte):
            continue
        if child.start_point.row == colon_node.end_point.row:
            after_colon_comment = Comment.from_cst(child)
            inline_comment_node = child
        else:
            between_comment_nodes.append(child)

    gap_start = (
        inline_comment_node.end_byte
        if inline_comment_node is not None
        else colon_node.end_byte
    )
    first_node = between_comment_nodes[0] if between_comment_nodes else body_node
    leading_gap = gap_from_offsets(node, gap_start, first_node.start_byte)
    leading_newlines = leading_gap.count("\n")
    if leading_newlines:
        breaks_after_semicolon = 1
        if leading_newlines > 1:
            before_body_trivia.extend(
                [empty_line] * (leading_newlines - 1)
            )

    for index, comment_node in enumerate(between_comment_nodes):
        before_body_trivia.append(Comment.from_cst(comment_node))
        next_node = (
            between_comment_nodes[index + 1]
            if index + 1 < len(between_comment_nodes)
            else body_node
        )
        gap = gap_between(node, comment_node, next_node)
        gap_newlines = gap.count("\n")
        if gap_newlines > 1:
            before_body_trivia.extend([empty_line] * (gap_newlines - 1))

    return (
        before_colon_comments,
        before_colon_gap,
        after_colon_comment,
        breaks_after_semicolon,
        before_body_trivia,
    )


@dataclass(slots=True)
class FunctionDefinition(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"function_expression"}
    argument_set: Identifier | list[Identifier | Ellipses] = field(default_factory=list)
    argument_set_is_multiline: bool | None = None
    argument_set_trailing_empty_lines: int = 0
    argument_set_trailing_comment_indent: int | None = None
    argument_set_inner_trivia: list[Any] = field(default_factory=list)
    named_attribute_set: Identifier | None = None
    named_attribute_set_before_formals: bool = False
    before_colon_comments: list[Any] = field(default_factory=list)
    before_colon_gap: str = ""
    breaks_after_semicolon: int | None = None
    after_colon_comment: Comment | None = None
    output: AttributeSet | NixExpression | None = None

    @classmethod
    def from_cst(cls, node: Node):
        """Capture argument layout (including empty-formal trivia) for round-trips."""
        if node.text is None:
            raise ValueError("Function definition has no code")

        (
            named_attribute_set,
            named_attribute_set_before_formals,
            argument_set,
            argument_set_is_multiline,
            argument_set_trailing_empty_lines,
            argument_set_inner_trivia,
            argument_set_trailing_comment_indent,
        ) = _parse_function_signature(node)

        body_node, output = _parse_function_body(node)
        (
            before_colon_comments,
            before_colon_gap,
            after_colon_comment,
            breaks_after_semicolon,
            before_body_trivia,
        ) = _collect_colon_trivia(node, body_node)

        _apply_before_body_trivia(output, before_body_trivia)

        return cls(
            breaks_after_semicolon=breaks_after_semicolon,
            argument_set=argument_set,
            named_attribute_set=named_attribute_set,
            named_attribute_set_before_formals=named_attribute_set_before_formals,
            before_colon_comments=before_colon_comments,
            before_colon_gap=before_colon_gap,
            after_colon_comment=after_colon_comment,
            output=output,
            argument_set_is_multiline=argument_set_is_multiline,
            argument_set_trailing_empty_lines=argument_set_trailing_empty_lines,
            argument_set_trailing_comment_indent=argument_set_trailing_comment_indent,
            argument_set_inner_trivia=argument_set_inner_trivia,
        )

    def _render_argument_set(
        self, *, base_indent: int, inner_indent: int
    ) -> tuple[str, bool]:
        """Render the argument set and resolve multiline behavior."""
        args_multiline = self.argument_set_is_multiline

        if not self.argument_set:
            args_multiline = False if args_multiline is None else args_multiline
            inner_trivia = list(self.argument_set_inner_trivia)
            has_layout_trivia = any(
                item in (empty_line, linebreak) for item in inner_trivia
            )
            inline_ok = (
                not args_multiline
                and not has_layout_trivia
                and self.argument_set_trailing_empty_lines == 0
                and inner_trivia
            )
            if inline_ok:
                comment_chunks: list[str] = []
                for item in inner_trivia:
                    if not isinstance(item, Comment):
                        inline_ok = False
                        break
                    rendered = item.rebuild(indent=0)
                    if "\n" in rendered:
                        inline_ok = False
                        break
                    comment_chunks.append(rendered)
                if inline_ok:
                    args_str = "{ " + " ".join(comment_chunks) + " }"
                else:
                    inline_ok = False
            if not inner_trivia and self.argument_set_trailing_empty_lines == 0:
                args_str = "{ }"
            elif not inline_ok:
                args_multiline = True
                inner_str = format_trivia(inner_trivia, indent=base_indent)
                if self.argument_set_trailing_empty_lines:
                    if inner_str and not inner_str.endswith("\n"):
                        inner_str += "\n"
                    inner_str += "\n" * self.argument_set_trailing_empty_lines
                closing_sep = "" if inner_str.endswith("\n") else "\n"
                args_str = (
                    "{\n"
                    + inner_str
                    + closing_sep
                    + " " * base_indent
                    + "}"
                )
            if self.named_attribute_set:
                if self.named_attribute_set_before_formals:
                    args_str = f"{self.named_attribute_set.rebuild()}@{args_str}"
                else:
                    args_str = f"{args_str}@{self.named_attribute_set.rebuild()}"
        elif isinstance(self.argument_set, Identifier):
            args_multiline = False if args_multiline is None else args_multiline
            args_str = self.argument_set.rebuild(indent=inner_indent, inline=True)
        else:
            if args_multiline is None:

                def argument_needs_multiline(arg: Identifier | Ellipses) -> bool:
                    """Detect arguments that force multiline formatting."""
                    if arg.before or arg.after:
                        return True
                    if isinstance(arg, Identifier) and arg.default_value is not None:
                        if arg.default_value_on_newline:
                            return True
                        default_inline = arg.default_value.rebuild(
                            indent=0, inline=True
                        )
                        if "\n" in default_inline:
                            return True
                    return False

                args_multiline = any(
                    argument_needs_multiline(arg) for arg in self.argument_set
                ) or len(self.argument_set) > 2
            args = []
            for i, arg in enumerate(self.argument_set):
                is_last_argument: bool = i == len(self.argument_set) - 1
                next_arg = (
                    self.argument_set[i + 1]
                    if i + 1 < len(self.argument_set)
                    else None
                )
                next_has_leading_comma = (
                    next_arg is not None
                    and hasattr(next_arg, "before")
                    and comma in next_arg.before
                )
                arg_expr = arg
                trailing_after: list[Any] = []
                if args_multiline and is_last_argument and arg.after:
                    inline_after: list[Any] = []
                    for item in arg.after:
                        if isinstance(item, Comment) and item.inline:
                            inline_after.append(item)
                        else:
                            trailing_after.append(item)
                    if trailing_after:
                        arg_expr = arg.model_copy(update={"after": inline_after})
                trailing_comma = args_multiline and not (
                    is_last_argument and isinstance(arg, Ellipses)
                )
                if next_has_leading_comma:
                    trailing_comma = False
                rendered = arg_expr.rebuild(
                    indent=inner_indent,
                    inline=not args_multiline,
                    trailing_comma=trailing_comma,
                )
                if trailing_after:
                    trailing_indent = inner_indent
                    if (
                        is_last_argument
                        and self.argument_set_trailing_comment_indent is not None
                    ):
                        trailing_indent = self.argument_set_trailing_comment_indent
                    rendered += apply_trailing_trivia(
                        "", trailing_after, indent=trailing_indent
                    )
                args.append(rendered)

            if args_multiline:
                trailing_gap = "\n" * self.argument_set_trailing_empty_lines
                args_str = (
                    "{\n"
                    + "\n".join(args)
                    + trailing_gap
                    + "\n"
                    + " " * base_indent
                    + "}"
                )
            else:
                args_str = "{ " + ", ".join(args) + " }"

            if self.named_attribute_set:
                if self.named_attribute_set_before_formals:
                    args_str = f"{self.named_attribute_set.rebuild()}@{args_str}"
                else:
                    args_str = f"{args_str}@{self.named_attribute_set.rebuild()}"

        return args_str, bool(args_multiline)

    def _render_output(
        self, *, args_multiline: bool, base_indent: int
    ) -> tuple[str, str]:
        """Render output expression and its line break separator."""
        args_are_formals = isinstance(self.argument_set, list)
        has_arguments = isinstance(self.argument_set, Identifier) or (
            isinstance(self.argument_set, list) and len(self.argument_set) > 0
        )
        output_has_scope = bool(
            self.output and getattr(self.output, "has_scope", lambda: False)()
        )
        output_multiline = False
        if self.output is not None:
            output_inline_preview = self.output.rebuild(
                indent=base_indent, inline=True
            )
            output_multiline = "\n" in output_inline_preview

        auto_breaks_after_semicolon = 1 if output_has_scope else 0
        if not auto_breaks_after_semicolon:
            if (args_are_formals and output_multiline) or (
                args_multiline and has_arguments
            ):
                auto_breaks_after_semicolon = 1

        breaks_after_semicolon = (
            self.breaks_after_semicolon
            if self.breaks_after_semicolon is not None
            else auto_breaks_after_semicolon
        )
        line_break = "\n" * breaks_after_semicolon
        output_inline = line_break == ""
        output_str = (
            self.output.rebuild(indent=base_indent, inline=output_inline)
            if self.output
            else "{ }"
        )
        return line_break, output_str

    def _format_colon_split(self, *, base_indent: int, line_break: str) -> str:
        """Format the colon separator with captured trivia."""
        comment_str = (
            f" {self.after_colon_comment.rebuild(indent=0)}"
            if self.after_colon_comment is not None
            else ""
        )
        colon_layout = layout_from_gap(self.before_colon_gap)
        if self.before_colon_comments:
            colon_layout = colon_layout.model_copy(update={"blank_line": False})

        force_colon_newline = any(
            item in (linebreak, empty_line)
            or (isinstance(item, Comment) and not item.inline)
            for item in self.before_colon_comments
        )
        if force_colon_newline and not colon_layout.on_newline:
            colon_layout = colon_layout.model_copy(
                update={
                    "on_newline": True,
                    "blank_line": any(
                        item is empty_line for item in self.before_colon_comments
                    ),
                }
            )

        inline_sep = " " if self.before_colon_comments else ""
        before_colon_str, colon_prefix = (
            format_interstitial_trivia_with_separator(
                self.before_colon_comments,
                colon_layout,
                indent=base_indent,
                inline_sep=inline_sep,
                drop_blank_line_if_items=False,
            )
        )
        if not line_break:
            return f"{before_colon_str}{colon_prefix}:{comment_str} "
        return f"{before_colon_str}{colon_prefix}:{comment_str}{line_break}"

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function definition."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        base_indent = indent
        inner_indent = indent + 2
        args_str, args_multiline = self._render_argument_set(
            base_indent=base_indent,
            inner_indent=inner_indent,
        )
        line_break, output_str = self._render_output(
            args_multiline=args_multiline,
            base_indent=base_indent,
        )
        split = self._format_colon_split(
            base_indent=base_indent,
            line_break=line_break,
        )
        core = f"{args_str}{split}{output_str}"
        return self.add_trivia(core, indent=base_indent, inline=inline)


__all__ = ["FunctionDefinition"]
