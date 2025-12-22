from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.source_code import NixSourceCode


def pretty_print_cst(node, indent_level=0) -> str:
    """Provide a quick CST debug view to diagnose parsing and trivia issues."""
    indent = "  " * indent_level
    match node:
        case Primitive():
            return f"{indent}{node.__class__.__name__}({node.value})"
        case NixList():
            return f"{indent}{node.__class__.__name__}({node.value})"
        case NixSourceCode():
            children = "\n".join(
                f"{indent}    {child}" for child in node.node.children
            )
            if children:
                return f"{indent}{node.__class__.__name__}({node.node}\n{children})"
            return f"{indent}{node.__class__.__name__}({node.node})"
        case _:
            raise ValueError(f"Unknown node type: {node}")
