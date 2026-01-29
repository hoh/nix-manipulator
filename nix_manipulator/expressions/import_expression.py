"""Import expressions with trivia-preserving formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tree_sitter import Node

from nix_manipulator.expressions.expression import (
    NixExpression,
    TypedExpression,
    coerce_expression,
)
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.identifier import Identifier


@dataclass(slots=True, repr=False)
class Import(TypedExpression):
    """Represent `import` expressions as first-class nodes.

    Note: `import` is a built-in function and can be shadowed. This node is a
    syntax-level marker only; resolution should not assume builtin semantics.
    """

    tree_sitter_types: ClassVar[set[str]] = {"apply_expression"}
    argument: NixExpression | None = None
    argument_gap: str | None = None
    import_after: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize primitive arguments to expression types."""
        NixExpression.__post_init__(self)
        if self.argument is not None and isinstance(
            self.argument, (str, int, bool, float)
        ):
            self.argument = coerce_expression(self.argument)

    @staticmethod
    def is_import_node(node: Node) -> bool:
        """Check whether *node* is an apply_expression for the `import` keyword."""
        function_node = node.child_by_field_name("function")
        return function_node is not None and function_node.text == b"import"

    @classmethod
    def from_cst(
        cls,
        node: Node,
        before: list[Any] | None = None,
        after: list[Any] | None = None,
    ) -> "Import":
        """Capture spacing/comments between `import` and its argument."""
        if not cls.is_import_node(node):
            raise ValueError("Not an import expression")

        call = FunctionCall.from_cst(node, before=before, after=after)
        name = call.name
        if not isinstance(name, Identifier) or name.name != "import":
            raise ValueError("Import expects the `import` identifier")
        return cls(
            argument=call.argument,
            argument_gap=call.argument_gap,
            import_after=call.function_after,
            before=call.before,
            after=call.after,
        )

    def rebuild(self, indent: int = 0, inline: bool = False) -> str:
        """Reconstruct import expressions while preserving layout trivia."""
        if self.has_scope():
            return self.rebuild_scoped(indent=indent, inline=inline)
        call = FunctionCall(
            name=Identifier(name="import"),
            argument=self.argument,
            argument_gap=self.argument_gap,
            function_after=self.import_after,
            before=self.before,
            after=self.after,
        )
        return call.rebuild(indent=indent, inline=inline)


__all__ = ["Import"]
