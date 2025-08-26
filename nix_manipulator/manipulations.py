from nix_manipulator.expressions import (
    AttributeSet,
    FunctionDefinition,
    NixExpression,
    NixSourceCode,
)
from nix_manipulator.parser import parse


def set_value(source: NixSourceCode, npath: str, value: str) -> str:
    value = parse(value).value[0]
    target: NixExpression = source.value[0]
    if isinstance(target, FunctionDefinition):
        target = target.output.argument
        target[npath] = value
        return source.rebuild()
    elif isinstance(target, AttributeSet):
        target[npath] = value
        return source.rebuild()
    else:
        raise ValueError("Unexpected expression type")


def remove_value(source: NixSourceCode, npath: str) -> str:
    target: NixExpression = source.value[0]
    if isinstance(target, FunctionDefinition):
        target = target.output.argument
        del target[npath]
        return source.rebuild()
    elif isinstance(target, AttributeSet):
        del target[npath]
        return source.rebuild()
    else:
        raise ValueError("Unexpected expression type")
