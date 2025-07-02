from pathlib import Path
from typing import List, Optional

import tree_sitter_nix as ts_nix
from tree_sitter import Language, Parser, Node

# Initialize the tree-sitter parser only once for efficiency.
NIX_LANGUAGE = Language(ts_nix.language())
PARSER = Parser(NIX_LANGUAGE)


def extract_text(node: Node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte : node.end_byte].decode("utf-8")


class CstNode:
    """Base class for all nodes in our Concrete Syntax Tree."""

    def __init__(self):
        # Trivia appearing immediately after this node (e.g., a comma, comments, newlines)
        self.post_trivia: List[CstLeaf] = []

    def rebuild(self) -> str:
        """Reconstruct the source code for this node, including any associated trivia."""
        post = "".join(t.rebuild() for t in self.post_trivia)
        return self._rebuild_internal() + post

    def _rebuild_internal(self) -> str:
        """Reconstruct the source code for the node itself, without trivia."""
        raise NotImplementedError


class CstContainer(CstNode):
    """A container node that holds a list of other CST nodes."""

    def __init__(self, children: List[CstNode]):
        super().__init__()
        self.children = children

    def __repr__(self):
        return f"{self.__class__.__name__}(children=[...])"

    def _rebuild_internal(self) -> str:
        return "".join(c.rebuild() for c in self.children)


class CstElement(CstContainer):
    """A generic container for non-specialized grammar elements."""

    def __init__(self, node_type: str, children: List[CstNode]):
        super().__init__(children)
        self.node_type = node_type

    def __repr__(self):
        return f"{self.__class__.__name__}(type='{self.node_type}', children=[...])"


class CstLeaf(CstNode):
    """Base class for leaf nodes in the CST, representing a literal piece of source code."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def __repr__(self):
        return f"{self.__class__.__name__}({self.text.strip()!r})"

    def _rebuild_internal(self) -> str:
        return self.text


class CstVerbatim(CstLeaf):
    """A generic leaf node for trivia or unknown tokens."""

    pass


# --- Specialized CST classes ---


class NixComment(CstLeaf):
    """A node representing a Nix comment."""

    pass


class NixIdentifier(CstLeaf):
    """A node representing a Nix identifier."""

    pass


class NixString(CstLeaf):
    """A node representing a Nix string."""

    pass


class NixBinding(CstContainer):
    """A node representing a Nix binding (e.g., `x = 1;`)."""

    pass


class NixAttrSet(CstContainer):
    """A node representing a Nix attribute set (e.g., `{ ... }`)."""

    pass


class NixLetIn(CstContainer):
    """A node representing a Nix let-in expression."""

    pass


class NixLambda(CstContainer):
    """A node representing a Nix lambda function (e.g., `x: ...`)."""

    pass


class NixFormal(CstContainer):
    """A node representing a formal parameter in a lambda."""

    @property
    def identifier(self) -> Optional[NixIdentifier]:
        """Returns the identifier of the formal parameter, if found."""
        for child in self.children:
            if isinstance(child, NixIdentifier):
                return child
        return None


NODE_TYPE_TO_CLASS = {
    "comment": NixComment,
    "identifier": NixIdentifier,
    "string_expression": NixString,
    "indented_string_expression": NixString,
    "binding": NixBinding,
    "attr_set": NixAttrSet,
    "let_in": NixLetIn,
    "lambda": NixLambda,
    "formal": NixFormal,
}


def parse_to_cst(node: Node, code: bytes) -> CstNode:
    """
    Recursively parse a Tree-sitter node into a Concrete Syntax Tree.
    This CST retains all characters from the original source file by attaching trivia
    (whitespace, comments) to the semantic nodes they belong to.
    """
    cls = NODE_TYPE_TO_CLASS.get(node.type)

    # If the node has no children, it's a leaf.
    if not node.children:
        text = extract_text(node, code)
        # Create a specialized leaf if a class is registered, otherwise a generic one.
        if cls and issubclass(cls, CstLeaf):
            return cls(text)
        return CstVerbatim(text)

    # --- Container Node Processing ---

    # 1. Create a temporary list of all CST nodes, including trivia between them.
    temp_list: List[CstNode] = []
    last_child_end = node.start_byte
    for child_node in node.children:
        trivia_text = code[last_child_end : child_node.start_byte].decode("utf-8")
        if trivia_text:
            temp_list.append(CstVerbatim(trivia_text))
        temp_list.append(parse_to_cst(child_node, code))
        last_child_end = child_node.end_byte

    final_trivia_text = code[last_child_end : node.end_byte].decode("utf-8")
    if final_trivia_text:
        temp_list.append(CstVerbatim(final_trivia_text))

    # 2. Process the temporary list to attach trivia to semantic nodes.
    final_children: List[CstNode] = []
    i = 0
    while i < len(temp_list):
        current_cst = temp_list[i]
        final_children.append(current_cst)

        # Look ahead for trivia to attach to the current node.
        j = i + 1
        while j < len(temp_list):
            next_cst = temp_list[j]
            # Attachable trivia includes comments and any verbatim leaf (e.g., commas, operators).
            if isinstance(next_cst, CstLeaf):
                current_cst.post_trivia.append(next_cst)
                j += 1
            else:
                break  # Stop when we hit the next non-leaf (semantic) node.

        # Advance the main loop counter past the trivia we just consumed.
        i = j

    # 3. Create the appropriate container for the processed children.
    if cls and issubclass(cls, CstContainer):
        return cls(final_children)
    return CstElement(node.type, final_children)


def parse_nix_cst(source_code: bytes) -> CstNode:
    """Parse Nix source code and return the root of its CST."""
    tree = PARSER.parse(source_code)
    return parse_to_cst(tree.root_node, source_code)


def parse_nix_file(file_path: Path) -> Optional[CstNode]:
    """Parse a Nix file and return the root of its CST."""
    try:
        source_code = file_path.read_bytes()
        return parse_nix_cst(source_code)
    except Exception as e:
        print(f"Error parsing file {file_path}: {e}")
        return None


def pretty_print_cst(node: CstNode, indent_level=0) -> str:
    """Generates a nicely indented string representation of the CST for printing."""
    indent = "  " * indent_level
    # Base representation for all nodes
    if isinstance(node, CstElement):
        base_repr = f"{indent}{node.__class__.__name__}(type='{node.node_type}'"
    elif isinstance(node, CstLeaf):
        base_repr = f"{indent}{node.__class__.__name__}({node.text!r}"
    else:
        base_repr = f"{indent}{node.__class__.__name__}("

    # Add post_trivia if it exists
    if node.post_trivia:
        base_repr += f", post_trivia=[...{len(node.post_trivia)} item(s)]"

    # Add children for containers
    if isinstance(node, CstContainer):
        base_repr += ", children=[\n"
        children_str = ",\n".join(
            pretty_print_cst(c, indent_level + 1) for c in node.children
        )
        footer = f"\n{indent}])"
        return base_repr + children_str + footer
    else:
        return base_repr + ")"
