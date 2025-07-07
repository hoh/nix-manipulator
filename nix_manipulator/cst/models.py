from __future__ import annotations

from nix_manipulator.expressions.expression import NixExpression
from nix_manipulator.expressions.binary import NixBinaryExpression
from nix_manipulator.expressions.comment import Comment
from nix_manipulator.expressions.function.call import FunctionCall
from nix_manipulator.expressions.function.definition import FunctionDefinition
from nix_manipulator.expressions.inherit import NixInherit
from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.path import NixPath
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.select import NixSelect
from nix_manipulator.expressions.set import NixAttributeSet, RecursiveAttributeSet
from nix_manipulator.expressions.source_code import NixSourceCode
from nix_manipulator.expressions.with_statement import NixWith

NODE_TYPE_TO_CLASS: dict[str, type[NixExpression]] = {
    "list_expression": NixList,
    "integer_expression": Primitive,
    "source_code": NixSourceCode,
    "apply_expression": FunctionCall,
    "comment": Comment,
    "string_expression": Primitive,
    "function_expression": FunctionDefinition,
    "variable_expression": Primitive,
    "attrset_expression": NixAttributeSet,
    "rec_attrset_expression": RecursiveAttributeSet,
    "binary_expression": NixBinaryExpression,
    "select_expression": NixSelect,
    "with_expression": NixWith,
    "inherit": NixInherit,
    "path_expression": NixPath,
}
