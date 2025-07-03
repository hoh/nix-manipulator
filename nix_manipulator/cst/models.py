from __future__ import annotations

from nix_manipulator.symbols import (
    Comment,
    FunctionCall,
    FunctionDefinition,
    NixExpression,
    NixList,
    NixObject,
    NixSourceCode,
)

NODE_TYPE_TO_CLASS: dict[str, type[NixObject]] = {
    "list_expression": NixList,
    "integer_expression": NixExpression,
    "source_code": NixSourceCode,
    "apply_expression": FunctionCall,
    "comment": Comment,
    "string_expression": NixExpression,
    "function_expression": FunctionDefinition,
    "variable_expression": NixExpression,
}
