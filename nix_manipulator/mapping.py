from __future__ import annotations

from nix_manipulator.expressions.binary import BinaryExpression
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import NixExpression, TypedExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.indented_string import IndentedString
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.let import LetExpression
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.path import NixPath
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.select import Select
from nix_manipulator.expressions.set import AttributeSet, RecursiveAttributeSet
from nix_manipulator.expressions.with_statement import WithStatement

EXPRESSION_TYPES: set[type[TypedExpression]] = {
    BinaryExpression,
    NixList,
    AttributeSet,
    RecursiveAttributeSet,
    Select,
    WithStatement,
    Inherit,
    NixPath,
    FunctionCall,
    FunctionDefinition,
    Comment,
    Primitive,
    LetExpression,
    Binding,
    IndentedString,
    Parenthesis,
    Ellipses,
}

TREE_SITTER_TYPE_TO_EXPRESSION: dict[str, type[TypedExpression]] = {
    tree_sitter_type: expression_type
    for expression_type in EXPRESSION_TYPES
    for tree_sitter_type in expression_type.tree_sitter_types
}


def tree_sitter_node_to_expression(node) -> NixExpression:
    return TREE_SITTER_TYPE_TO_EXPRESSION[node.type].from_cst(node)
