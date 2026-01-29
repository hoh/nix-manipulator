"""Inherit statement parsing with explicit whitespace preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.identifier import Identifier
from nix_manipulator.expressions.layout import empty_line, linebreak
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.trivia import (
    append_comment_between,
    append_gap_between_offsets,
    gap_between,
    layout_from_gap,
    separator_from_layout,
    trim_leading_layout_trivia,
)


@dataclass(slots=True, repr=False)
class Inherit(TypedExpression):
    """Represent `inherit` statements, keeping their original spacing."""

    tree_sitter_types: ClassVar[set[str]] = {"inherit", "inherit_from"}
    names: list[Identifier | Primitive]
    from_expression: NixExpression | None = None
    after_inherit_gap: str = " "
    parenthesis_open_gap: str = ""
    parenthesis_close_gap: str = ""
    after_expression_gap: str = " "
    name_gaps: list[str] = field(default_factory=list)
    after_names_gap: str = ""

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ):
        """Preserve inherit layout so name sourcing remains readable."""
        names: list[Identifier | Primitive] = []
        inherited_attrs: Node | None = None
        inherit_node: Node | None = None
        open_paren: Node | None = None
        close_paren: Node | None = None
        last_name_node: Node | None = None

        for child in node.children:
            if child.type == "inherit":
                inherit_node = child
            elif child.type == "inherited_attrs":
                inherited_attrs = child
            elif child.type == "(":
                open_paren = child
            elif child.type == ")":
                close_paren = child

        from_expression: NixExpression | None = None
        from_node = node.child_by_field_name("expression")
        if from_node is not None:
            from nix_manipulator.mapping import tree_sitter_node_to_expression

            from_expression = tree_sitter_node_to_expression(from_node)

        after_inherit_gap = " "
        after_expression_gap = " "
        name_gaps: list[str] = []
        after_names_gap = ""
        parenthesis_open_gap = ""
        parenthesis_close_gap = ""
        semicolon_node = next(
            (child for child in node.children if child.type == ";"), None
        )

        if inherited_attrs is not None and inherit_node is not None:
            if (
                from_node is not None
                and open_paren is not None
                and close_paren is not None
            ):
                after_inherit_gap = gap_between(node, inherit_node, open_paren)
                parenthesis_open_gap = gap_between(node, open_paren, from_node)
                after_expression_gap = gap_between(node, close_paren, inherited_attrs)
                parenthesis_close_gap = gap_between(node, from_node, close_paren)
            else:
                after_inherit_gap = gap_between(node, inherit_node, inherited_attrs)

            before_names: list[Any] = []
            outer_comments = [
                child for child in node.children if child.type == "comment"
            ]
            leading_comments = [
                comment
                for comment in outer_comments
                if comment.start_byte < inherited_attrs.start_byte
            ]
            trailing_comments = []
            if semicolon_node is not None:
                trailing_comments = [
                    comment
                    for comment in outer_comments
                    if inherited_attrs.end_byte
                    < comment.start_byte
                    < semicolon_node.start_byte
                ]

            prev_outer: Node | None = None
            start_outer = close_paren if close_paren is not None else inherit_node
            for comment_node in leading_comments:
                prev_gap_node = prev_outer if prev_outer is not None else start_outer
                append_comment_between(before_names, node, prev_gap_node, comment_node)
                prev_outer = comment_node
            prev_content: Node | None = prev_outer

            def parse_name(
                child: Node, before_names: list[Any]
            ) -> Identifier | Primitive:
                """Normalize inherit names for consistent rendering rules."""
                if child.type == "identifier":
                    return Identifier.from_cst(child, before=before_names)
                if child.type == "string_expression":
                    name_expr = Primitive.from_cst(child)
                    if before_names:
                        name_expr = name_expr.model_copy(
                            update={"before": before_names}
                        )
                    return name_expr
                raise ValueError(f"Unsupported inherit attr type: {child.type}")

            for child in inherited_attrs.children:
                if child.type == "comment":
                    if prev_content is not None:
                        append_gap_between_offsets(
                            before_names, node, prev_content, child
                        )
                    comment = Comment.from_cst(child)
                    inline_to_prev = (
                        last_name_node is not None
                        and child.start_point.row == last_name_node.end_point.row
                        and names
                    )
                    if inline_to_prev:
                        comment.inline = True
                        names[-1].after.append(comment)
                    else:
                        before_names.append(comment)
                    prev_content = child
                    continue

                if child.type in ("identifier", "string_expression"):
                    if prev_content is not None:
                        append_gap_between_offsets(
                            before_names, node, prev_content, child
                        )
                    if last_name_node is not None:
                        name_gaps.append(gap_between(node, last_name_node, child))
                    name_expr = parse_name(child, before_names)
                    names.append(name_expr)
                    before_names = []
                    prev_content = child
                    last_name_node = child
                    continue

            if before_names and names:
                names[-1].after.extend(before_names)

            if trailing_comments and names:
                trailing_trivia: list[Any] = []
                prev_trailing: Node | None = last_name_node
                for comment_node in trailing_comments:
                    comment = append_comment_between(
                        trailing_trivia, node, prev_trailing, comment_node
                    )
                    if (
                        last_name_node is not None
                        and comment_node.start_point.row == last_name_node.end_point.row
                    ):
                        comment.inline = True
                    prev_trailing = comment_node
                if trailing_trivia:
                    names[-1].after.extend(trailing_trivia)

        if semicolon_node is not None:
            prev_node: Node | None = None
            if last_name_node is not None:
                prev_node = last_name_node
            elif close_paren is not None:
                prev_node = close_paren
            elif from_node is not None:
                prev_node = from_node
            if prev_node is not None:
                after_names_gap = gap_between(node, prev_node, semicolon_node)

        return cls(
            names=names,
            from_expression=from_expression,
            after_inherit_gap=after_inherit_gap,
            parenthesis_open_gap=parenthesis_open_gap,
            parenthesis_close_gap=parenthesis_close_gap,
            after_expression_gap=after_expression_gap,
            name_gaps=name_gaps,
            after_names_gap=after_names_gap,
            before=before or [],
            after=after or [],
        )

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct the inherit statement."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        def render_name_with_gap(name: NixExpression, gap: str) -> str:
            """Honor captured gaps so inherit names keep their spacing."""
            layout = layout_from_gap(gap)
            if not layout.on_newline:
                sep = separator_from_layout(layout, indent=indent)
                return f"{sep}{name.rebuild(indent=indent, inline=True)}"
            target_indent = layout.indent if layout.indent is not None else indent
            sep = "\n\n" if layout.blank_line else "\n"
            trimmed_before = trim_leading_layout_trivia(name.before)
            has_visible_before = any(
                item not in (linebreak, empty_line) for item in trimmed_before
            )
            if trimmed_before == name.before:
                name_to_render = name
            else:
                name_to_render = name.model_copy(update={"before": trimmed_before})
            if has_visible_before:
                return (
                    f"{sep}{name_to_render.rebuild(indent=target_indent, inline=False)}"
                )
            if target_indent:
                sep += " " * target_indent
            return f"{sep}{name_to_render.rebuild(indent=target_indent, inline=True)}"

        def render_names(first_gap: str) -> str:
            """Render all inherit names with their recorded separators."""
            rendered = render_name_with_gap(self.names[0], first_gap)
            for gap, name in zip(self.name_gaps, self.names[1:]):
                rendered += render_name_with_gap(name, gap)
            return rendered

        def append_chunk(base: str, chunk: str) -> str:
            """Avoid double newlines when concatenating formatted pieces."""
            if base.endswith("\n") and chunk.startswith("\n"):
                return base + chunk[1:]
            return base + chunk

        def gap_is_multiline(gap: str) -> bool:
            """Summarize gap layout to guide multiline formatting choices."""
            return layout_from_gap(gap).on_newline

        def name_requires_multiline(name: NixExpression) -> bool:
            """Detect trivia that forces multiline inherit formatting."""
            for item in name.before + name.after:
                if item in (linebreak, empty_line):
                    return True
                if isinstance(item, Comment) and not item.inline:
                    return True
            return False

        names_gaps: list[str] = []
        if self.from_expression is None:
            names_gaps.append(self.after_inherit_gap)
        else:
            names_gaps.append(self.after_expression_gap)
        names_gaps.extend(self.name_gaps)
        names_gaps.append(self.after_names_gap)

        names_multiline = any(gap_is_multiline(gap) for gap in names_gaps if gap)
        if not names_multiline:
            names_multiline = any(name_requires_multiline(name) for name in self.names)

        source_multiline = False
        if self.from_expression is not None:
            source_gaps = [
                self.after_inherit_gap,
                self.parenthesis_open_gap,
                self.parenthesis_close_gap,
            ]
            source_multiline = any(gap_is_multiline(gap) for gap in source_gaps if gap)
            if not source_multiline:
                source_preview = self.from_expression.rebuild(
                    indent=indent, inline=True
                )
                source_multiline = "\n" in source_preview

        inherit_layout = layout_from_gap(self.after_inherit_gap)
        open_paren_layout = layout_from_gap(self.parenthesis_open_gap)
        close_paren_layout = layout_from_gap(self.parenthesis_close_gap)
        semicolon_layout = layout_from_gap(self.after_names_gap)

        def render_inherit_source(*, force_newline: bool) -> str:
            """Render inherit source with captured gaps to preserve intent."""
            rebuild_string = "inherit"
            if self.from_expression is None:
                return rebuild_string
            if force_newline:
                inherit_sep = "\n" + " " * (indent + 2)
                from_indent = indent + 2
            else:
                inherit_sep = separator_from_layout(inherit_layout, indent=indent)
                from_indent = indent
                if inherit_layout.on_newline and inherit_layout.indent is not None:
                    from_indent = inherit_layout.indent
                if (
                    not force_newline
                    and open_paren_layout.on_newline
                    and open_paren_layout.indent is not None
                ):
                    from_indent = open_paren_layout.indent
            if (
                open_paren_layout.on_newline
                and open_paren_layout.indent is not None
                and force_newline
                and open_paren_layout.indent == 0
            ):
                from_indent = indent + 2
            from_expression = self.from_expression
            if open_paren_layout.on_newline:
                trimmed_before = trim_leading_layout_trivia(from_expression.before)
                if trimmed_before != from_expression.before:
                    from_expression = from_expression.model_copy(
                        update={"before": trimmed_before}
                    )
            expr_inline = True
            open_sep = separator_from_layout(
                open_paren_layout, indent=from_indent, inline_sep=""
            )
            if open_paren_layout.on_newline:
                open_sep = "\n\n" if open_paren_layout.blank_line else "\n"
                expr_inline = False
            expr_str = from_expression.rebuild(indent=from_indent, inline=expr_inline)
            close_sep = separator_from_layout(
                close_paren_layout, indent=from_indent, inline_sep=""
            )
            if close_sep.startswith("\n") and expr_str.endswith("\n"):
                close_sep = close_sep[1:]
            rebuild_string += f"{inherit_sep}({open_sep}{expr_str}{close_sep})"
            return rebuild_string

        if names_multiline or source_multiline:
            name_indent = indent + 2
            name_gap = "\n" + " " * name_indent

            force_inherit_newline = source_multiline and not inherit_layout.on_newline
            rebuild_string = render_inherit_source(force_newline=force_inherit_newline)

            if self.names:
                rendered_names = ""
                for name in self.names:
                    gap = name_gap
                    if any(item is empty_line for item in name.before):
                        gap = "\n\n" + " " * name_indent
                    chunk = render_name_with_gap(name, gap)
                    rendered_names = (
                        chunk
                        if not rendered_names
                        else append_chunk(rendered_names, chunk)
                    )
                rebuild_string = append_chunk(rebuild_string, rendered_names)

            semicolon_indent = " " * name_indent
            if rebuild_string.endswith("\n"):
                rebuild_string += f"{semicolon_indent};"
            else:
                rebuild_string += f"\n{semicolon_indent};"
            return self.add_trivia(rebuild_string, indent, inline)

        rebuild_string = render_inherit_source(force_newline=False)
        if self.from_expression is not None:
            if self.names:
                rebuild_string += render_names(self.after_expression_gap)
        elif self.names:
            rebuild_string += render_names(self.after_inherit_gap)
        semicolon_sep = separator_from_layout(
            semicolon_layout, indent=indent, inline_sep=""
        )
        rebuild_string += f"{semicolon_sep};"
        return self.add_trivia(rebuild_string, indent, inline)


__all__ = ["Inherit"]
