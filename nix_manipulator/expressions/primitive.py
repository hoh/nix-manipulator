from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.identifier import Identifier


def _escape_nix_string(value: str, *, escape_interpolation: bool = False) -> str:
    """Escape string content so rebuilds emit valid Nix.

    When *escape_interpolation* is True, `${` is escaped to keep strings
    literal (useful for attr names); normal string values should keep
    interpolation intact.
    """
    escaped: list[str] = []
    index = 0
    while index < len(value):
        ch = value[index]
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        elif ch == "\r":
            escaped.append("\\r")
        elif ch == "\t":
            escaped.append("\\t")
        elif (
            escape_interpolation
            and ch == "$"
            and index + 1 < len(value)
            and value[index + 1] == "{"
        ):
            escaped.append("\\${")
            index += 2
            continue
        else:
            escaped.append(ch)
        index += 1
    return "".join(escaped)


@dataclass(slots=True, eq=False, repr=False)
class Primitive(TypedExpression):
    """Base class for primitive literals with shared operator helpers."""

    tree_sitter_types: ClassVar[set[str]] = {
        "integer_expression",
        "string_expression",
        "variable_expression",
    }
    value: Any
    raw_string: bool = False

    def __new__(cls, *args, **kwargs):
        """Dispatch to concrete subclasses when the base class is instantiated."""
        if cls is Primitive:
            value = kwargs.get("value", args[0] if args else None)
            target_cls = _primitive_cls_from_value(value)
            if target_cls is not Primitive:
                return object.__new__(target_cls)
        return object.__new__(cls)

    def __post_init__(self) -> None:
        """Normalize scope containers defined on the base expression."""
        NixExpression.__post_init__(self)

    def __eq__(self, other: object) -> bool:
        """Support equality against primitives while keeping expression structure."""
        if isinstance(other, Primitive):
            return (
                self.value == other.value
                and self.raw_string == other.raw_string
                and self.before == other.before
                and self.after == other.after
                and self.scope == other.scope
                and self.scope_state == other.scope_state
            )
        if isinstance(other, NixExpression):
            return False
        return self.value == other

    def _coerce_other_value(self, other: Any) -> Any:
        """Extract Python payloads from other primitives."""
        if isinstance(other, Primitive):
            return other.value
        return other

    @classmethod
    def from_cst(cls, node: Node):
        """Normalize primitives while keeping literal string escapes intact."""
        text = node.text
        if text is None:
            raise ValueError("Missing expression")

        match node.type:
            case "string_expression":
                bytes_ = text
                if bytes_.startswith(b'"') and bytes_.endswith(b'"'):
                    bytes_ = bytes_[1:-1]
                string_value = bytes_.decode()
                return StringPrimitive(value=string_value, raw_string=True)
            case "string_fragment":
                fragment_value = text.decode()
                return StringPrimitive(value=fragment_value, raw_string=True)
            case "integer_expression":
                return IntegerPrimitive(value=int(text))
            case "variable_expression":
                if text in (b"true", b"false"):
                    bool_value = text == b"true"
                    return BooleanPrimitive(value=bool_value)
                if text == b"null":
                    return NullPrimitive()
                return Identifier(name=text.decode())
            case _:
                raise ValueError(f"Unsupported expression type: {node.type}")

    def _render_value(self) -> str:
        """Render the primitive payload."""
        raise ValueError(f"Unsupported expression type: {type(self.value)}")

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct expression while escaping strings to preserve semantics."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)

        value_str = self._render_value()
        return self.add_trivia(value_str, indent, inline)


@dataclass(slots=True, eq=False, repr=False)
class IntegerPrimitive(Primitive):
    """Integer literal with operator support."""

    value: int

    def _coerce_int(self, other: Any) -> int:
        other_value = self._coerce_other_value(other)
        if isinstance(other_value, bool):
            return int(other_value)
        if not isinstance(other_value, int):
            raise TypeError(
                f"unsupported operand type(s) for +: 'int' and '{type(other_value).__name__}'"
            )
        return other_value

    def __add__(self, other: Any):
        other_value = self._coerce_int(other)
        new_value = self.value + other_value
        return self.model_copy(update={"value": new_value})

    def __radd__(self, other: Any):
        return self.__add__(other)

    def __iadd__(self, other: Any):
        other_value = self._coerce_int(other)
        self.value += other_value
        return self

    def _render_value(self) -> str:
        return f"{self.value}"


@dataclass(slots=True, eq=False, repr=False)
class BooleanPrimitive(Primitive):
    """Boolean literal."""

    value: bool

    def _render_value(self) -> str:
        return "true" if self.value else "false"


@dataclass(slots=True, eq=False, repr=False)
class StringPrimitive(Primitive):
    """String literal with concatenation helpers."""

    value: str

    def _coerce_str(self, other: Any) -> str:
        other_value = self._coerce_other_value(other)
        if not isinstance(other_value, str):
            raise TypeError(
                f"unsupported operand type(s) for +: 'str' and '{type(other_value).__name__}'"
            )
        return other_value

    def __add__(self, other: Any):
        other_value = self._coerce_str(other)
        new_value = f"{self.value}{other_value}"
        return self.model_copy(update={"value": new_value, "raw_string": False})

    def __radd__(self, other: Any):
        other_value = self._coerce_str(other)
        new_value = f"{other_value}{self.value}"
        return self.model_copy(update={"value": new_value, "raw_string": False})

    def __iadd__(self, other: Any):
        other_value = self._coerce_str(other)
        self.value = f"{self.value}{other_value}"
        self.raw_string = False
        return self

    def _render_value(self) -> str:
        raw_value = self.value if self.raw_string else _escape_nix_string(self.value)
        return f'"{raw_value}"'


@dataclass(slots=True, eq=False, repr=False)
class NullPrimitive(Primitive):
    """Null literal."""

    value: None = None

    def _render_value(self) -> str:
        return "null"


def _primitive_cls_from_value(value: Any) -> type[Primitive]:
    """Select the concrete primitive class for a Python value."""
    if isinstance(value, bool):
        return BooleanPrimitive
    if value is None:
        return NullPrimitive
    if isinstance(value, int):
        return IntegerPrimitive
    if isinstance(value, str):
        return StringPrimitive
    return Primitive


__all__ = [
    "BooleanPrimitive",
    "IntegerPrimitive",
    "NullPrimitive",
    "Primitive",
    "StringPrimitive",
]
