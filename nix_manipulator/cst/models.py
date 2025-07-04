from __future__ import annotations

from nix_manipulator.symbols import (
    Comment,
    FunctionCall,
    FunctionDefinition,
    NixAttributeSet,
    NixBinaryExpression,
    NixList,
    NixObject,
    NixSourceCode,
    Primitive,
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
    "binary_expression": NixBinaryExpression,
}
