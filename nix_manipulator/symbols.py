from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel
from tree_sitter import Node


class EmptyLine:
    pass


class Linebreak:
    pass


class Comma:
    pass


empty_line = EmptyLine()
linebreak = Linebreak()
comma = Comma()


class NixObject(BaseModel):
    """Base class for all Nix objects."""

    before: List[Any] = []
    after: List[Any] = []

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
                # result += str(item)
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
    recursive: bool = False
    argument_set: List[NixIdentifier] = []
    let_statements: List[NixBinding] = []
    result: Union[NixAttributeSet, NixObject, None] = None

    @classmethod
    def from_cst(cls, node: Node):
        print("F", node, node.type, dir(node), node.text)
        raise NotImplementedError
        # name = node.text
        # argument_set = []
        # let_statements = []
        # result = None
        # recursive = False
        # for child in node.children:
        #     print("C", child, child.type, dir(child), child.text)

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
            for arg in self.argument_set:
                indented_line = " " * indent + f"{arg.name}"
                print([indented_line])
                args.append(f"{self._format_trivia(arg.before, indent)}{indented_line}")

            # Add a trailing comma to the last argument
            if args:
                args[-1] += ","

            args_str = "{\n" + ",\n".join(args) + "\n}"

        # Build let statements
        let_str = ""
        if self.let_statements:
            let_bindings: List[str] = []
            for binding in self.let_statements:
                let_bindings.append(binding.rebuild(indent=2))
            let_str = "let\n" + "\n".join(let_bindings) + "\nin\n"

        # Build result
        result_str = self.result.rebuild() if self.result else "{ }"

        # Format the final string - use single line format when no arguments and no let statements
        if not self.argument_set and not self.let_statements:
            return f"{before_str}{args_str}: {result_str}{after_str}"
        else:
            return f"{before_str}{args_str}:\n{let_str}{result_str}{after_str}"


class NixIdentifier(NixObject):
    name: str

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        indentation = " " * indent if not inline else ""
        print("ID", [self.name, self.before, before_str, indent, inline])
        return f"{before_str}{indentation}{self.name}{after_str}"


class Comment(NixObject):
    text: str

    def __str__(self):
        lines = self.text.split("\n")
        return "\n".join(f"# {line}" for line in lines)

    @classmethod
    def from_cst(cls, node: Node):
        print("C", node, node.type, dir(node), node.text)
        if node.text is None:
            raise ValueError("Missing comment")
        text = node.text.decode()
        if text.startswith("#"):
            text = text[1:]
            if text.startswith(" "):
                text = text[1:]
        return cls(text=text)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        print("INN DENT", indent, [self.text])
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

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct binding."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        print("BINDING", [self.name, self.value, self.before, before_str, indent])

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild(indent=indent, inline=True)
        elif isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        else:
            raise ValueError(f"Unsupported value type: {type(self.value)}")

        # Apply indentation to the entire binding, not just the value
        indented_line = " " * indent + f"{self.name} = {value_str};"

        print("BINDING RESULT", [f"{before_str}{indented_line}{after_str}"])

        return f"{before_str}{indented_line}{after_str}"

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        before = before or []
        after = after or []

        print("B", node, node.type, dir(node), node.text)
        print(len(node.children), node.children)
        children = (
            node.children[0].children if len(node.children) == 1 else node.children
        )
        for child in children:
            if child.type in ("=", ";"):
                continue
            elif child.type in "attrpath":
                name = child.text.decode()
            elif child.type == "string_expression":
                value = NixExpression(value=json.loads(child.text.decode()))
            elif child.type == "integer_expression":
                value = NixExpression(value=int(child.text.decode()))
            # elif child.type == "identifier":
            #     print("X", child, child.type, dir(child), child.text)
            #     for attr in dir(child):
            #         print("-", attr, "=", getattr(child, attr))
            #     name = child.text.decode()
            #     value = "FAKE"
            else:
                raise ValueError(f"Unsupported child node: {child}")

        return cls(name=name, value=value, before=before, after=after)


class NixAttributeSet(NixObject):
    values: List[NixBinding]

    @classmethod
    def from_dict(cls, values: Dict[str, NixObject]):
        values_list = []
        for key, value in values.items():
            values_list.append(NixBinding(name=key, value=value))
        return cls(values=values_list)

    @classmethod
    def from_cst(cls, node: Node):
        print("A", node, node.type, dir(node), node.text)
        values = []
        for child in node.children:
            print("C", child, child.type, dir(child), child.text)
            if child.type in ("{", "}"):
                continue
            elif child.type == "binding_set":
                if child.named_children:
                    comment = None
                    for grandchild in child.named_children:
                        if grandchild.type == "binding":
                            if not comment:
                                values.append(
                                    NixBinding.from_cst(grandchild),
                                )
                            else:
                                values.append(
                                    NixBinding.from_cst(grandchild, before=[comment]),
                                )
                                comment = None
                                continue
                        elif grandchild.type == "comment":
                            comment = Comment.from_cst(grandchild)
                            continue
                        else:
                            raise ValueError(f"Unknown binding child: {grandchild}")
                    if comment:
                        # No binding followed the comment so it could not be attached to it
                        values[-1].after.append(comment)
                else:
                    values.append(
                        NixBinding.from_cst(child),
                    )
            else:
                raise ValueError(f"Unsupported child node: {child}")

        return cls(values=values)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)

        if not self.values:
            return f"{before_str}{{ }}{after_str}"

        bindings_str = "\n".join(
            [value.rebuild(indent=indented, inline=inline) for value in self.values]
        )
        return (
            f"{before_str}{{" + f"\n{bindings_str}\n" + " " * indent + f"}}{after_str}"
        )


class FunctionCall(NixObject):
    name: str
    argument: Optional[NixAttributeSet] = None
    recursive: bool = False

    @classmethod
    def from_cst(cls, node: Node):
        if not node.text:
            raise ValueError("Missing function name")
        name = node.text.decode()
        argument = None
        recursive = False
        for child in node.children:
            if child.type == "select_expression":
                name = child.text.decode()
            elif child.type == "attrset_expression":
                argument = NixAttributeSet.from_cst(child)
            elif child.type == "rec":
                recursive = True
        return cls(name=name, argument=argument, recursive=recursive)

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct function call."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)
        indentation = "" if inline else " " * indent

        print(
            "FC",
            [
                self.name,
                self.argument,
                self.recursive,
                self.before,
                before_str,
                indent,
                indentation,
            ],
        )

        if not self.argument:
            return f"{before_str}{indentation}{self.name}{after_str}"

        args = []
        for binding in self.argument.values:
            args.append(binding.rebuild(indent=indented))

        indented_items = [f"{item}" for item in args]
        args_str = " {\n" + "\n".join(indented_items) + "\n" + " " * indent + "}"

        rec_str = " rec" if self.recursive else ""
        return f"{before_str}{indentation}{self.name}{rec_str}{args_str}{after_str}"


class NixExpression(NixObject):
    value: Union[str, int, bool]

    @classmethod
    def from_cst(cls, node: Node):
        if node.text is None:
            raise ValueError("Missing expression")

        print("N", node, node.type, dir(node), node.text)
        if node.type == "string_expression":
            value = json.loads(node.text)
        elif node.type == "integer_expression":
            value = int(node.text)
        elif node.type == "variable_expression":
            assert node.text in (b"true", b"false")
            value = node.text == b"true"
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
            if isinstance(item, NixExpression):
                items.append(f"{item.rebuild(indent=indent if inline else indented)}")
            elif isinstance(item, NixIdentifier):
                items.append(
                    f"{item.rebuild(indent=indented if (inline or self.multiline) else indented, inline=not self.multiline)}"
                )
            elif isinstance(item, NixObject):
                items.append(f"{item.rebuild(indent=indent if inline else indented)}")
            elif isinstance(item, str):
                items.append(f'{indentation}"{item}"')
            elif isinstance(item, bool):
                items.append(f"{indentation}{'true' if item else 'false'}")
            elif isinstance(item, int):
                items.append(f"{indentation}{item}")
            else:
                raise ValueError(f"Unsupported list item type: {type(item)}")

        print("I", items, self.multiline, indented, [indentation], self.multiline)

        if self.multiline:
            # Add proper indentation for multiline lists
            items_str = "\n".join(items)
            print("item_str", [items_str])
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
    expression: NixIdentifier
    attributes: List[NixIdentifier] = []

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct with expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        # expr_str = self.expression.rebuild() if self.expression else ""
        attrs_str = " ".join(attr.name for attr in self.attributes)

        return f"{before_str}with {self.expression.name}; [ {attrs_str} ]{after_str}"
