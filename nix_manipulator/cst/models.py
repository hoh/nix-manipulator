from __future__ import annotations

from nix_manipulator.symbols import (
    Comment,
    FunctionCall,
    FunctionDefinition,
    NixAttributeSet,
    NixBinaryExpression,
    NixInherit,
    NixList,
    NixObject,
    NixPath,
    NixSelect,
    NixSourceCode,
    NixWith,
    Primitive,
    RecursiveAttributeSet,
)

NODE_TYPE_TO_CLASS: dict[str, type[NixObject]] = {
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
