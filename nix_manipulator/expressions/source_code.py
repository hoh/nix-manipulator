from __future__ import annotations

from typing import Any, ClassVar, List

from pydantic import ConfigDict
from tree_sitter import Node


class NixSourceCode:
    tree_sitter_types: ClassVar[set[str]] = {"source_code"}
    node: Node
    value: List[Any]

    model_config = ConfigDict(extra="forbid")

    def __init__(self, node: Node, value: List[Any]):
        self.node = node
        self.value = value

    @classmethod
    def from_cst(cls, node: Node) -> NixSourceCode:
        from nix_manipulator.mapping import tree_sitter_node_to_expression

        value = [tree_sitter_node_to_expression(obj) for obj in node.children]
        return cls(node=node, value=value)

    def rebuild(self) -> str:
        return "".join(obj.rebuild() for obj in self.value)

    def __repr__(self) -> str:
        return f"NixSourceCode(\n  node={self.node}, \n  value={self.value}\n)"


__all__ = ["NixSourceCode"]
