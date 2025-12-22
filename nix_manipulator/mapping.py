from __future__ import annotations

from nix_manipulator.expressions.assertion import Assertion
from nix_manipulator.expressions.binary import BinaryExpression
from nix_manipulator.expressions.binding import Binding
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.ellipses import Ellipses
from nix_manipulator.expressions.expression import (NixExpression,
                                                    TypedExpression)
from nix_manipulator.expressions.float import FloatExpression
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.has_attr import HasAttrExpression
from nix_manipulator.expressions.if_expression import IfExpression
from nix_manipulator.expressions.indented_string import IndentedString
from nix_manipulator.expressions.inherit import Inherit
from nix_manipulator.expressions.let import LetExpression, parse_let_expression
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.parenthesis import Parenthesis
from nix_manipulator.expressions.path import NixPath
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.select import Select
from nix_manipulator.expressions.set import AttributeSet
from nix_manipulator.expressions.unary import UnaryExpression
from nix_manipulator.expressions.with_statement import WithStatement

EXPRESSION_TYPES: set[type[TypedExpression]] = {
    Assertion,
    BinaryExpression,
    NixList,
    AttributeSet,
    Select,
    WithStatement,
    Inherit,
    NixPath,
    FunctionCall,
    FunctionDefinition,
    Comment,
    Primitive,
    FloatExpression,
    LetExpression,
    Binding,
    IndentedString,
    Parenthesis,
    Ellipses,
    UnaryExpression,
    IfExpression,
    HasAttrExpression,
}

TREE_SITTER_TYPE_TO_EXPRESSION: dict[str, type[TypedExpression]] = {
    tree_sitter_type: expression_type
    for expression_type in EXPRESSION_TYPES
    for tree_sitter_type in expression_type.tree_sitter_types
}


def register_expression(cls: type[TypedExpression]) -> type[TypedExpression]:
    """Allow extensions to plug in new expressions without editing core maps."""
    EXPRESSION_TYPES.add(cls)
    for tree_sitter_type in cls.tree_sitter_types:
        TREE_SITTER_TYPE_TO_EXPRESSION[tree_sitter_type] = cls
    return cls


def tree_sitter_node_to_expression(node) -> NixExpression:
    """Centralize CST-to-expression mapping to keep parsing rules consistent."""
    if node.type == "let_expression":
        return parse_let_expression(node)
    expression_type = TREE_SITTER_TYPE_TO_EXPRESSION.get(node.type)
    if expression_type is None:
        raise ValueError(f"Unsupported node type: {node.type}")
    return expression_type.from_cst(node)
