from __future__ import annotations

import json
from typing import Dict, List, Union, Any

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

    def rebuild(self, indent: int = 0) -> str:
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
                result += item.rebuild(indent=indent)
            else:
                raise NotImplementedError(f"Unsupported trivia item: {item}")
                # result += str(item)
        return result


class FunctionDefinition(NixObject):
    recursive: bool = False
    argument_set: List[NixIdentifier] = []
    let_statements: List[NixBinding] = []
    result: Union[NixAttributeSet, NixObject, None] = None

    @classmethod
    def from_cst(cls, node: Node):
        print("F", node, node.type, dir(node), node.text)
        name = node.text
        argument_set = []
        let_statements = []
        result = None
        recursive = False
        for child in node.children:
            print("C", child, child.type, dir(child), child.text)

    def rebuild(self, indent: int = 0) -> str:
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
            let_str = f"let\n" + "\n".join(let_bindings) + "\nin\n"

        # Build result
        result_str = self.result.rebuild() if self.result else "{ }"

        # Format the final string - use single line format when no arguments and no let statements
        if not self.argument_set and not self.let_statements:
            return f"{before_str}{args_str}: {result_str}{after_str}"
        else:
            return f"{before_str}{args_str}:\n{let_str}{result_str}{after_str}"


class NixIdentifier(NixObject):
    name: str

    def __init__(self, name: str, **kwargs):
        super().__init__(name=name, **kwargs)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)
        return f"{before_str}{self.name}{after_str}"


class Comment(NixObject):
    text: str

    def __str__(self):
        lines = self.text.split("\n")
        return "\n".join(f"# {line}" for line in lines)

    @classmethod
    def from_cst(cls, node: Node):
        print("C", node, node.type, dir(node), node.text)
        return cls(text=node.text.decode())

    def rebuild(self, indent: int = 0) -> str:
        return " " * indent + str(self) + "\n"


class MultilineComment(Comment):
    def rebuild(self, indent: int = 0) -> str:
        if "\n" in self.text:
            # Multiline
            text = self.text
            result: str
            if self.text.startswith("\n"):
                result = " " * indent + "/*"
            else:
                result = "/* "

            result += self.text.replace("\n", "\n" + " " * indent)

            if not self.text.endswith("\n"):
                result += " */"
            else:
                result += "*/\n"
            return result
        else:
            # Single line
            return f"/* {self.text} */"


class NixBinding(NixObject):
    name: str
    value: Union[NixObject, str, int, bool]

    def __init__(self, name: str, value, **kwargs: Any):
        super().__init__(name=name, value=value, **kwargs)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct binding."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild(indent=indent)
        elif isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        else:
            value_str = str(self.value)

        # Apply indentation to the entire binding, not just the value
        indented_line = " " * indent + f"{self.name} = {value_str};"

        return f"{before_str}{indented_line}{after_str}"

    @classmethod
    def from_cst(cls, node: Node):
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
            elif child.type == "identifier":
                print("X", child, child.type, dir(child), child.text)
                for attr in dir(child):
                    print("-", attr, "=", getattr(child, attr))
                name = child.text.decode()
                value = "FAKE"
            else:
                raise ValueError(f"Unsupported child node: {child}")
        return cls(name=name, value=value)


class NixAttributeSet(NixObject):
    values: List[NixBinding]

    def __init__(self, values: List[NixBinding] | Dict[str, NixObject], **kwargs):
        # Convert dict to
        if isinstance(values, dict):
            values_list = []
            for key, value in values.items():
                values_list.append(NixBinding(key, value))
            values = values_list

        print("V", [values])

        super().__init__(values=values, **kwargs)

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
                    for grandchild in child.named_children:
                        if grandchild.type == "binding":
                            values.append(
                                NixBinding.from_cst(grandchild),
                            )
                        else:
                            raise ValueError(f"Unknown binding child: {grandchild}")
                else:
                    values.append(
                        NixBinding.from_cst(child),
                    )
            else:
                raise ValueError(f"Unsupported child node: {child}")

        return cls(values=values)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct attribute set."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)

        if not self.values:
            return f"{before_str}{{ }}{after_str}"

        bindings_str = "\n".join(
            [value.rebuild(indent=indented) for value in self.values]
        )
        return (
            f"{before_str}{{" + f"\n{bindings_str}\n" + " " * indent + f"}}{after_str}"
        )


class FunctionCall(NixObject):
    name: str
    argument: NixAttributeSet = None
    recursive: bool = False

    @classmethod
    def from_cst(cls, node: Node):
        print("F", node, node.type, dir(node), node.text)
        name = node.text
        argument = None
        recursive = False
        for child in node.children:
            print("C", child, child.type, dir(child), child.text)
            if child.type == "select_expression":
                name = child.text.decode()
                print(f"name = {name}")
            elif child.type == "attrset_expression":
                argument = NixAttributeSet.from_cst(child)
            elif child.type == "rec":
                recursive = True
        return cls(name=name, argument=argument, recursive=recursive)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct function call."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)

        if not self.argument:
            return f"{before_str}{self.name}{after_str}"

        args = []
        for binding in self.argument.values:
            args.append(binding.rebuild(indent=indented))

        args_str: str = " {\n" + "\n".join(args) + "\n" + " " * indent + "}"
        rec_str = " rec" if self.recursive else ""
        return f"{before_str}{self.name}{rec_str}{args_str}{after_str}"


class NixExpression(NixObject):
    value: Union[str, int, bool]

    @classmethod
    def from_cst(cls, node: Node):
        print("N", node, node.type, dir(node), node.text)
        # return parse_to_cst(node)
        return cls(value=json.loads(node.text))

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild(indent=indent)
        elif isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        else:
            value_str = str(self.value)

        return f"{before_str}{value_str}{after_str}"


class NixList(NixExpression):
    value: List[Union[NixObject, str, int, bool]]
    multiline: bool = True

    def __init__(self, value, multiline: bool = True, **kwargs):
        super().__init__(value=value, multiline=multiline, **kwargs)

    @classmethod
    def from_cst(cls, node: Node):
        from nix_manipulator.cst.parser import parse_to_cst

        value = [
            parse_to_cst(obj) for obj in node.children if obj.type not in ("[", "]")
        ]
        return cls(value=value)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct list."""
        indented = indent + 2
        before_str = self._format_trivia(self.before, indent=indented)
        after_str = self._format_trivia(self.after, indent=indented)

        if not self.value:
            return f"{before_str}[]{after_str}"

        items = []
        for item in self.value:
            if isinstance(item, NixObject):
                items.append(f"{item.rebuild(indent=indented)}")
            elif isinstance(item, str):
                items.append(f'"{item}"')
            elif isinstance(item, bool):
                items.append(f"{'true' if item else 'false'}")
            else:
                items.append(f"{str(item)}")

        if self.multiline:
            # Add proper indentation for multiline lists
            indented_items = [" " * indented + f"{item}" for item in items]
            items_str = "\n".join(indented_items)
            return f"{before_str}[\n{items_str}\n" + " " * indent + f"]{after_str}"
        else:
            items_str = " ".join(items)
            return f"{before_str}[ {items_str} ]{after_str}"


class NixWith(NixObject):
    expression: NixIdentifier
    attributes: List[NixIdentifier] = []

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct with expression."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        # expr_str = self.expression.rebuild() if self.expression else ""
        attrs_str = " ".join(attr.name for attr in self.attributes)

        return f"{before_str}with {self.expression.name}; [ {attrs_str} ]{after_str}"
