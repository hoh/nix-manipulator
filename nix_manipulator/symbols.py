from __future__ import annotations
from pydantic import BaseModel
from typing import Dict, List, Union, Any
from collections import OrderedDict

empty_line = object()
linebreak = object()
comma = object()


class NixObject(BaseModel):
    """Base class for all Nix objects."""
    before: List[Any] = []
    after: List[Any] = []

    def rebuild(self) -> str:
        """Reconstruct the Nix source code for this object."""
        raise NotImplementedError

    def _format_trivia(self, trivia_list: List[Any]) -> str:
        """Convert trivia objects to string representation."""
        result = ""
        for item in trivia_list:
            if item is empty_line:
                result += "\n\n"
            elif item is linebreak:
                result += "\n"
            elif item is comma:
                result += ","
            elif isinstance(item, (Comment, MultilineComment)):
                result += str(item)
            else:
                result += str(item)
        return result


class FunctionDefinition(NixObject):
    name: str
    recursive: bool = False
    argument_set: List[NixIdentifier] = []
    let_statements: List[NixBinding] = []
    result: Union[NixSet, NixObject] = None

    def rebuild(self) -> str:
        """Reconstruct function definition."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        # Build argument set
        args = []
        for arg in self.argument_set:
            args.append(f"{self._format_trivia(arg.before)}{arg.name}")

        args_str = "{\n  " + ",\n  ".join(args) + "\n}"

        # Build let statements
        let_str = ""
        if self.let_statements:
            let_bindings = []
            for binding in self.let_statements:
                let_bindings.append(f"  {binding.rebuild()}")
            let_str = f"let\n" + "\n".join(let_bindings) + "\nin\n"

        # Build result
        result_str = self.result.rebuild() if self.result else "{}"

        return f"{before_str}{args_str}:\n{let_str}{result_str}{after_str}"


class NixIdentifier(NixObject):
    name: str

    def __init__(self, name: str, **kwargs):
        super().__init__(name=name, **kwargs)

    def rebuild(self) -> str:
        """Reconstruct identifier."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)
        return f"{before_str}{self.name}{after_str}"


class Comment(NixObject):
    text: str

    def __str__(self):
        return f"# {self.text}"

    def rebuild(self) -> str:
        return str(self)


class MultilineComment(Comment):
    def __str__(self):
        return f"/* {self.text} */"


class NixBinding(NixObject):
    name: str
    value: Union[NixObject, str, int, bool]

    def rebuild(self) -> str:
        """Reconstruct binding."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild()
        elif isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        else:
            value_str = str(self.value)

        return f"{before_str}{self.name} = {value_str};{after_str}"


class NixSet(NixObject):
    values: Dict[str, Union[NixObject, str, int, bool]]

    def __init__(self, values: Dict[str, Any], **kwargs):
        # Convert to OrderedDict to preserve order
        if not isinstance(values, OrderedDict):
            values = OrderedDict(values)
        super().__init__(values=values, **kwargs)

    def rebuild(self) -> str:
        """Reconstruct attribute set."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        if not self.values:
            return f"{before_str}{{}}{after_str}"

        bindings = []
        for key, value in self.values.items():
            if isinstance(value, NixObject):
                value_str = value.rebuild()
            elif isinstance(value, str):
                value_str = f'"{value}"'
            elif isinstance(value, bool):
                value_str = "true" if value else "false"
            else:
                value_str = str(value)

            bindings.append(f"  {key} = {value_str};")

        bindings_str = "\n".join(bindings)
        return f"{before_str}{{\n{bindings_str}\n}}{after_str}"


class FunctionCall(NixObject):
    name: str
    arguments: List[NixBinding] = []

    def rebuild(self) -> str:
        """Reconstruct function call."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        if not self.arguments:
            return f"{before_str}{self.name}{after_str}"

        args = []
        for arg in self.arguments:
            args.append(f"  {arg.rebuild()}")

        args_str = " {\n" + "\n".join(args) + "\n}"
        return f"{before_str}{self.name}{args_str}{after_str}"


class NixExpression(NixObject):
    value: Union[NixObject, str, int, bool]

    def rebuild(self) -> str:
        """Reconstruct expression."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        if isinstance(self.value, NixObject):
            value_str = self.value.rebuild()
        elif isinstance(self.value, str):
            value_str = f'"{self.value}"'
        elif isinstance(self.value, bool):
            value_str = "true" if self.value else "false"
        else:
            value_str = str(self.value)

        return f"{before_str}{value_str}{after_str}"


class NixList(NixExpression):
    value: List[Union[NixObject, str, int, bool]]

    def rebuild(self) -> str:
        """Reconstruct list."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        if not self.value:
            return f"{before_str}[]{after_str}"

        items = []
        for item in self.value:
            if isinstance(item, NixObject):
                items.append(f"  {item.rebuild()}")
            elif isinstance(item, str):
                items.append(f'  "{item}"')
            elif isinstance(item, bool):
                items.append(f'  {"true" if item else "false"}')
            else:
                items.append(f"  {str(item)}")

        items_str = "\n".join(items)
        return f"{before_str}[\n{items_str}\n]{after_str}"


class NixWith(NixObject):
    expression: NixIdentifier
    attributes: List[NixIdentifier] = []

    def rebuild(self) -> str:
        """Reconstruct with expression."""
        before_str = self._format_trivia(self.before)
        after_str = self._format_trivia(self.after)

        expr_str = self.expression.rebuild() if self.expression else ""
        attrs_str = " ".join(attr.rebuild() for attr in self.attributes)

        return f"{before_str}with {expr_str}; {attrs_str}{after_str}"