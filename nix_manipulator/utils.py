from nix_manipulator.expressions.list import NixList
from nix_manipulator.expressions.primitive import Primitive
from nix_manipulator.expressions.source_code import NixSourceCode


def pretty_print_cst(node, indent_level=0) -> str:
    indent = "  " * indent_level
    # Base representation for all nodes
    if isinstance(node, Primitive):
        base_repr = f"{indent}{node.__class__.__name__}({node.value}'"
    elif isinstance(node, NixList):
        base_repr = f"{indent}{node.__class__.__name__}({node.value}"
    elif isinstance(node, NixSourceCode):
        base_repr = f"{indent}{node.__class__.__name__}({node.node}"
        for child in node.node.children:
            base_repr += f"\n{indent}    {child}"
        base_repr += ")"
    else:
        raise ValueError(f"Unknown node type: {node}")

    # # Add post_trivia if it exists
    # if node.post_trivia:
    #     base_repr += f", post_trivia=[...{node.post_trivia} item(s)]"

    # # Add children for containers
    # if isinstance(node, CstContainer):
    #     base_repr += ", children=[\n"
    #     children_str = ",\n".join(
    #         pretty_print_cst(c, indent_level + 1) for c in node.children
    #     )
    #     footer = f"\n{indent}])"
    #     return base_repr + children_str + footer
    # else:
    return base_repr + ")"
