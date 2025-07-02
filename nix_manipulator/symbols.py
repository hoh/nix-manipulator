from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Union, Any

from pydantic import BaseModel

empty_line = object()
linebreak = object()
comma = object()


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
            # elif item is linebreak:
            #     result += "\n"
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
                args.append(f"{self._format_trivia(arg.before, indent)}{indented_line}")
            args_str = "{\n  " + ",\n".join(args) + "\n}"

        # Build let statements
        let_str = ""
        if self.let_statements:
            let_bindings: List[str] = []
            for binding in self.let_statements:
                let_bindings.append(binding.rebuild(indent=2))
            let_str = f"let\n" + "\n".join(let_bindings) + "\nin\n"

        # Build result
        result_str = self.result.rebuild() if self.result else "{}"

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

    def rebuild(self, indent: int = 0) -> str:
        return " " * indent + str(self) + "\n"


class MultilineComment(Comment):
    def __str__(self):
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


class NixAttributeSet(NixObject):
    values: List[NixBinding]

    def __init__(self, values: List[NixBinding] | Dict[str, NixObject], **kwargs):
        # Convert dict to
        if isinstance(values, dict):
            values_list = []
            for key, value in values.items():
                values_list.append(NixBinding(key, value))
            values = values_list

        super().__init__(values=values, **kwargs)

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct attribute set."""
        indent += 2
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if not self.values:
            return f"{before_str}{{ }}{after_str}"

        bindings_str = "\n".join(
            [value.rebuild(indent=indent) for value in self.values]
        )
        return f"{before_str}{{\n{bindings_str}\n}}{after_str}"


class FunctionCall(NixObject):
    name: str
    argument: NixAttributeSet = NixAttributeSet({})
    recursive: bool = False

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct function call."""
        indent += 2
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if not self.argument:
            return f"{before_str}{self.name}{after_str}"

        args = []
        for binding in self.argument.values:
            args.append(binding.rebuild(indent=indent))

        args_str: str = " {\n" + "\n".join(args) + "\n}"
        rec_str = " rec" if self.recursive else ""
        return f"{before_str}{self.name}{rec_str}{args_str}{after_str}"


class NixExpression(NixObject):
    value: Union[NixObject, str, int, bool]

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

    def rebuild(self, indent: int = 0) -> str:
        """Reconstruct list."""
        before_str = self._format_trivia(self.before, indent=indent)
        after_str = self._format_trivia(self.after, indent=indent)

        if not self.value:
            return f"{before_str}[]{after_str}"

        items = []
        for item in self.value:
            if isinstance(item, NixObject):
                items.append(f"{item.rebuild()}")
            elif isinstance(item, str):
                items.append(f'"{item}"')
            elif isinstance(item, bool):
                items.append(f"{'true' if item else 'false'}")
            else:
                items.append(f"{str(item)}")

        if self.multiline:
            # Add proper indentation for multiline lists
            indented_items = [f"  {item}" for item in items]
            items_str = "\n".join(indented_items)
            return f"{before_str}[\n{items_str}\n]{after_str}"
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

        return f"{before_str}with {self.expression.name}; [ {attrs_str} ];{after_str}"
