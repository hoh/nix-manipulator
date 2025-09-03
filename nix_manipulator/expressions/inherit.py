from __future__ import annotations

from typing import Any, ClassVar, List, Optional

from tree_sitter import Node

from nix_manipulator.expressions.expression import TypedExpression
from nix_manipulator.expressions.identifier import Identifier


class Inherit(TypedExpression):
    tree_sitter_types: ClassVar[set[str]] = {"inherit"}
    names: List[Identifier]
    from_identifier: Optional[Identifier] = None

    @classmethod
    def from_cst(
        cls, node: Node, before: List[Any] | None = None, after: List[Any] | None = None
    ):
        names: list[Identifier]
        for child in node.children:
            if child.type == "inherited_attrs":
                names = [
                    Identifier.from_cst(grandchild) for grandchild in child.children
                ]
                break
        else:
            names = []

        from_identifier: Optional[Identifier] = None
        from_node = node.child_by_field_name("expression")
        if from_node is not None:
            name_node = from_node.child_by_field_name("name")
            if name_node is not None and name_node.type == "identifier":
                from_identifier = Identifier.from_cst(name_node)

        return cls(
            names=names,
            from_identifier=from_identifier,
            before=before or [],
            after=after or [],
        )

    def rebuild(
        self,
        indent: int = 0,
        inline: bool = False,
    ) -> str:
        """Reconstruct the inherit statement."""
        names = " ".join(name.rebuild(inline=True) for name in self.names)
        prefix = ""
        if self.from_identifier is not None:
            prefix = f"({self.from_identifier.rebuild(inline=True)}) "
        return self.add_trivia(f"inherit {prefix}{names};", indent, inline)


__all__ = ["Inherit"]
