from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node

logger = logging.getLogger(__name__)


class EmptyLine:
    def __repr__(self):
        return "EmptyLine"


class Linebreak:
    def __repr__(self):
        return "Linebreak"


class Comma:
    def __repr__(self):
        return "Comma"


empty_line = EmptyLine()
linebreak = Linebreak()
comma = Comma()


class NixObject(BaseModel):
    """Base class for all Nix objects."""

    model_config = ConfigDict(extra="forbid")

    before: List[Any] = Field(default_factory=list)
    after: List[Any] = Field(default_factory=list)

    @classmethod
    def from_cst(cls, node: Node):
        """Construct an object from a CST node."""
        raise NotImplementedError

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct the Nix source code for this object."""
        raise NotImplementedError

    def _format_trivia(self, trivia_list: List[Any], indent: int = 0) -> str:
        """Convert trivia objects to string representation."""
        result = ""
        for item in trivia_list:
            if item is empty_line:
                result += "\n"
            elif item is linebreak:
                result += ""
            elif item is comma:
                result += ","
            elif isinstance(item, (Comment, MultilineComment)):
                result += item.rebuild(indent=indent) + "\n"
            else:
                raise NotImplementedError(f"Unsupported trivia item: {item}")
        return result


class NixSourceCode:
    node: Node
    value: List[Any]

    def __init__(self, node: Node, value: List[Any]):
        self.node = node
        self.value = value

    @classmethod
    def from_cst(cls, node: Node) -> NixSourceCode:
        from nix_manipulator.cst.parser import parse_to_cst

        value = [parse_to_cst(obj) for obj in node.children]
        return cls(node=node, value=value)

    def rebuild(self) -> str:
        return "".join(obj.rebuild() for obj in self.value)

    def __repr__(self) -> str:
        return f"NixSourceCode(\n  node={self.node}, \n  value={self.value}\n)"


class FunctionDefinition(NixObject):
    argument_set: List[NixIdentifier] = []
    argument_set_is_multiline: bool = True
    breaks_after_semicolon: Optional[int] = None
    let_statements: List[NixBinding] = []
    output: Union[NixAttributeSet, NixObject, None] = None

    @classmethod
    def from_cst(cls, node: Node):
        children_types = [child.type for child in node.children]
        assert children_types in (
            ["formals", ":", "attrset_expression"],
            ["formals", ":", "apply_expression"],
        ), (
            f"Output other than attrset_expression not supported yet. You used {children_types}"
        )

        argument_set = []
        argument_set_is_multiline = b"\n" in node.child_by_field_name("formals").text

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
                for grandchild in child.children:
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
                            NixIdentifier.from_cst(grandchild, before=before)
                        )
                        before = []
                    else:
                        raise ValueError(
                            f"Unsupported child node: {grandchild} {grandchild.type}"
                        )
            elif child.type == "comment":
                if previous_child:
                    gap = node.text[previous_child.end_byte : child.start_byte].decode()
                    is_empty_line = False
                    if re.match(r"[ ]*\n[ ]*\n[ ]*", gap):
                        before.append(empty_line)
                        is_empty_line = True

                before.append(Comment.from_cst(child))
            elif child.type == "ERROR" and child.text == b",":
                logger.debug(
                    "Trailing commas are RFC compliant but add a 'ERROR' element..."
                )
            else:
                raise ValueError(f"Unsupported child node: {child} {child.type}")
            previous_child = child

        if before:
            # No binding followed the comment so it could not be attached to it
            argument_set[-1].after += before

        let_statements = []

        body: Node = node.child_by_field_name("body")
        if body.type == "attrset_expression":
            output: NixObject = NixAttributeSet.from_cst(body)
        elif body.type == "apply_expression":
            output: NixObject = FunctionCall.from_cst(body)
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
            let_statements=let_statements,
            output=output,
            argument_set_is_multiline=argument_set_is_multiline,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function definition."""
        indent += 2
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        # Build argument set
        if not self.argument_set:
            args_str = "{ }"
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

        # Build let statements
        let_str = ""
        if self.let_statements:
            let_bindings: List[str] = []
            for binding in self.let_statements:
                let_bindings.append(binding.rebuild(indent=2))
            let_str = "let\n" + "\n".join(let_bindings) + "\nin\n"

        # Build result)
        output_str = self.output.rebuild() if self.output else "{ }"

        breaks_after_semicolon: int
        if self.breaks_after_semicolon is not None:
            breaks_after_semicolon = self.breaks_after_semicolon
        elif self.let_statements:
            breaks_after_semicolon = 1
        else:
            breaks_after_semicolon = (
                1
                if self.let_statements
                or (self.argument_set_is_multiline and len(self.argument_set) > 0)
                else 0
            )
        line_break = "\n" * breaks_after_semicolon

        # Format the final string - use single line format when no arguments and no let statements
        if (not self.argument_set) and (not self.let_statements):
            split = ": " if not line_break else ":" + line_break
            return f"{before_str}{args_str}{split}{output_str}{after_str}"
        else:
            split = ": " if not line_break else ":" + line_break
            return f"{before_str}{args_str}{split}{let_str}{output_str}{after_str}"


class NixIdentifier(NixObject):
    name: str

    @classmethod
    def from_cst(cls, node: Node, before: List[Any] | None = None):
        name = node.text.decode()
        return cls(name=name, before=before or [])

    def rebuild(
        self, indent: int = 0, inline: bool = False, trailing_comma: bool = False
    ) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        comma = "," if trailing_comma else ""

        if self.after and self.after[-1] != linebreak and after_str[-1] == "\n":
            after_str = after_str[:-1]

        indentation = " " * indent if not inline else ""
        return f"{before_str}{indentation}{self.name}{comma}" + (
            f"\n{after_str}" if after_str else ""
        )


class NixInherit(NixObject):
    names: List[NixIdentifier]

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        names: list[NixIdentifier]
        for child in node.children:
            if child.type == "inherited_attrs":
                names = [
                    NixIdentifier.from_cst(grandchild) for grandchild in child.children
                ]
                break
        else:
            names = []

        return cls(names=names, before=before or [], after=after or [])

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if self.after and self.after[-1] != linebreak and after_str[-1] == "\n":
            after_str = after_str[:-1]

        indentation = " " * indent if not inline else ""
        names = " ".join(name.rebuild(inline=True) for name in self.names)
        return f"{before_str}{indentation}inherit {names};" + (
            f"\n{after_str}" if after_str else ""
        )


class NixPath(NixObject):
    path: str

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        path = node.text.decode()
        return cls(path=path, before=before or [], after=after or [])

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indentation = " " * indent if not inline else ""
        return f"{before_str}{indentation}{self.path}{after_str}"


class Comment(NixObject):
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


class NixBinding(NixObject):
    name: str
    value: Union[NixObject, str, int, bool]
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
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent

        # Decide how the *value* itself has to be rendered
        val_indent = indent + 2 if self.newline_after_equals else indent

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild(indent=val_indent, inline=not self.newline_after_equals)
        elif isinstance(self.value, str):
            value_str = (" " * val_indent if self.newline_after_equals else "") + f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = (" " * val_indent if self.newline_after_equals else "") + ("true" if self.value else "false")
        elif isinstance(self.value, int):
            value_str = (" " * val_indent if self.newline_after_equals else "") + str(self.value)
        else:
            raise ValueError(f"Unsupported value type: {type(self.value)}")

        # Assemble left-hand side
        head = f"{indentation}{self.name} ="
        sep = "\n" if self.newline_after_equals else " "
        core = f"{head}{sep}{value_str};"

        if self.after and isinstance(self.after[0], Comment):
            inline_comment = self.after[0].rebuild(indent=0)
            trailing = self._format_trivia(self.after[1:], indent=indent)
            return f"{before_str}{core} {inline_comment}{trailing}"

        if self.after and self.after[0] is linebreak:
            trailing = self._format_trivia(self.after[1:], indent=indent)
            if not trailing.startswith("\n"):
                trailing = "\n" + trailing
            if trailing.endswith("\n"):
                trailing = trailing[:-1]
            return f"{before_str}{core}{trailing}"

        if self.after and self.after[-1] is not linebreak and after_str.endswith("\n"):
            after_str = after_str[:-1]

        return f"{before_str}{core}" + (f"\n{after_str}" if after_str else "")


class NixAttributeSet(NixObject):
    values: List[NixBinding | NixInherit | FunctionCall]
    multiline: bool = True
    recursive: bool = False

    @classmethod
    def from_dict(cls, values: Dict[str, NixObject]):
        values_list = []
        for key, value in values.items():
            values_list.append(NixBinding(name=key, value=value))
        return cls(values=values_list)

    @classmethod
    def from_cst(cls, node: Node) -> "NixAttributeSet":
        """
        Parse an attr-set, preserving comments and blank lines.

        Handles both the outer `attrset_expression` and the inner
        `binding_set` wrapper that tree-sitter-nix inserts.
        """
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
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)

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


class FunctionCall(NixObject):
    name: str
    argument: Optional[NixObject] = None
    recursive: bool = False
    multiline: bool = True

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        multiline = b"\n" in node.text

        if not node.text:
            raise ValueError("Missing function name")
        name = node.child_by_field_name("function").text.decode()

        recursive = (
            node.child_by_field_name("argument").type == "rec_attrset_expression"
        )

        from .cst.parser import parse_to_cst

        argument = parse_to_cst(node.child_by_field_name("argument"))

        return cls(
            name=name,
            argument=argument,
            recursive=recursive,
            multiline=multiline,
            before=before or [],
            after=after or [],
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function call."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)
        indentation = "" if inline else " " * indent

        if not self.argument:
            return f"{before_str}{indentation}{self.name}{after_str}"

        if False:
            args = []
            for binding in self.argument.values:
                args.append(binding.rebuild(indent=indented, inline=not self.multiline))

            indented_items = [f"{item}" for item in args]

            if self.multiline:
                args_str = (
                    " {\n" + "\n".join(indented_items) + "\n" + " " * indent + "}"
                )
            else:
                items_str = " ".join(indented_items)
                args_str = f" {{ {items_str} }}"
        else:
            args_str = self.argument.rebuild(indent=indent, inline=not self.multiline)

        rec_str = " rec" if self.recursive else ""
        return f"{before_str}{indentation}{self.name}{rec_str} {args_str}{after_str}"


class Primitive(NixObject):
    value: Union[str, int, bool]

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing expression")

        if node.type == "string_expression":
            value = json.loads(node.text)
        elif node.type == "string_fragment":
            value = node.text.decode()
        elif node.type == "integer_expression":
            value = int(node.text)
        elif node.type == "variable_expression":
            if node.text in (b"true", b"false"):
                value = node.text == b"true"
            else:
                return NixIdentifier(name=node.text.decode())
        else:
            raise ValueError(f"Unsupported expression type: {node.type}")
        return cls(value=value)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        indentation = "" if inline else " " * indent

        if isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        elif isinstance(self.value, int):
            value_str = f"{self.value}"
        else:
            raise ValueError(f"Unsupported expression type: {type(self.value)}")

        return f"{before_str}{indentation}{value_str}{after_str}"

    def __repr__(self):
        return f"NixExpression(\nvalue={self.value} type={type(self.value)}\n)"


class NixList(NixObject):
    value: List[Union[NixObject, str, int, bool]]
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.cst.parser import parse_to_cst

        if node.text is None:
            raise ValueError("List has no code")

        multiline = b"\n" in node.text

        value = [
            parse_to_cst(obj) for obj in node.children if obj.type not in ("[", "]")
        ]
        return cls(value=value, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct list."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indented = indent + 2 if self.multiline else indent
        indentation = "" if inline else " " * indented

        if not self.value:
            return f"{before_str}[]{after_str}"

        items = []
        for item in self.value:
            if isinstance(item, Primitive):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, NixIdentifier):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, NixObject):
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


class NixWith(NixObject):
    environment: NixObject
    body: NixObject
    multiline: bool = True

    @classmethod
    def from_cst(cls, node: Node):
        environment_node = node.child_by_field_name("environment")
        body_node = node.child_by_field_name("body")
        multiline = b"\n" in node.text

        from nix_manipulator.cst.models import NODE_TYPE_TO_CLASS

        def parse_to_cst_(node: Node) -> NixObject:
            assert node.type
            node_class: type[NixObject] = NODE_TYPE_TO_CLASS[node.type]
            return node_class.from_cst(node)

        environment = parse_to_cst_(environment_node)
        body = parse_to_cst_(body_node)
        return cls(environment=environment, body=body, multiline=multiline)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct with expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        # expr_str = self.expression.rebuild() if self.expression else ""
        # attrs_str = " ".join(attr.name for attr in self.attributes)

        environment_str = self.environment.rebuild(indent=indent, inline=True)
        body_str = self.body.rebuild(indent=indent, inline=True)

        return f"{before_str}with {environment_str}; {body_str}{after_str}"


class NixExpression(NixObject):
    pass


class NixBinaryExpression(NixExpression):
    operator: str
    left: NixObject
    right: NixObject

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.cst.models import NODE_TYPE_TO_CLASS

        if node.type == "binary_expression":
            left_node, operator_node, right_node = node.children
            operator = operator_node.text.decode()
            left = NODE_TYPE_TO_CLASS.get(left_node.type).from_cst(left_node)
            right = NODE_TYPE_TO_CLASS.get(right_node.type).from_cst(right_node)
        return cls(operator=operator, left=left, right=right)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binary expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent

        left_str = self.left.rebuild(indent=indent, inline=True)
        right_str = self.right.rebuild(indent=indent, inline=True)

        return f"{before_str}{indentation}{left_str} {self.operator} {right_str}{after_str}"


class NixSelect(NixObject):
    expression: NixIdentifier
    attribute: NixIdentifier

    @classmethod
    def from_cst(cls, node: Node) -> NixSelect:
        return cls(
            expression=NixIdentifier(
                name=node.child_by_field_name("expression").text.decode()
            ),
            attribute=NixIdentifier(
                name=node.child_by_field_name("attrpath").text.decode()
            ),
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct select expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indentation = "" if inline else " " * indent
        return f"{before_str}{indentation}{self.expression.name}.{self.attribute.name}{after_str}"
