
#!/usr/bin/env python3
"""
A python library and tool powerful enough to be used into IPython solely that
intent to make the process of writing code that modify Nix source code as easy
and as simple as possible.

That includes writing custom refactoring, generic refactoring, tools, IDE or
directly modifying your Nix source code via IPython with a higher and more
powerful abstraction than the advanced text modification tools that you find in
advanced text editors and IDE.

This project guarantees you that it will only modify your code where you ask
him to. To achieve this, it is based on tree-sitter, a multilingual AST.
"""

import argparse
from pathlib import Path
from typing import List, Optional

import tree_sitter_nix as ts_nix
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer
from pygments.lexers.python import PythonLexer
from tree_sitter import Language, Parser, Node

# Initialize the tree-sitter parser only once for efficiency.
NIX_LANGUAGE = Language(ts_nix.language())
PARSER = Parser(NIX_LANGUAGE)


def extract_text(node: Node, code: bytes) -> str:
    """Extract the exact source substring for a node."""
    return code[node.start_byte:node.end_byte].decode('utf-8')


class CstNode:
    """Base class for all nodes in our Concrete Syntax Tree."""

    def rebuild(self) -> str:
        raise NotImplementedError


class CstContainer(CstNode):
    """A container node that holds a list of other CST nodes."""

    def __init__(self, children: List[CstNode]):
        self.children = children

    def __repr__(self):
        return f"{self.__class__.__name__}(children=[...])"

    def rebuild(self) -> str:
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
        self.text = text

    def __repr__(self):
        return f"{self.__class__.__name__}({self.text.strip()!r})"

    def rebuild(self) -> str:
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


NODE_TYPE_TO_CLASS = {
    "comment": NixComment,
    "identifier": NixIdentifier,
    "string_expression": NixString,
    "indented_string_expression": NixString,
    "binding": NixBinding,
    "attr_set": NixAttrSet,
    "let_in": NixLetIn,
    "lambda": NixLambda,
}


def parse_to_cst(node: Node, code: bytes) -> CstNode:
    """
    Recursively parse a Tree-sitter node into a Concrete Syntax Tree.
    This CST retains all characters from the original source file, including
    whitespace and comments, ensuring a perfect rebuild.
    """
    cls = NODE_TYPE_TO_CLASS.get(node.type)

    if not node.children:
        text = extract_text(node, code)
        if cls and issubclass(cls, CstLeaf):
            return cls(text)
        return CstVerbatim(text)

    children_cst: List[CstNode] = []
    last_child_end = node.start_byte
    for child in node.children:
        trivia = code[last_child_end:child.start_byte].decode('utf-8')
        if trivia:
            children_cst.append(CstVerbatim(trivia))
        children_cst.append(parse_to_cst(child, code))
        last_child_end = child.end_byte

    final_trivia = code[last_child_end:node.end_byte].decode('utf-8')
    if final_trivia:
        children_cst.append(CstVerbatim(final_trivia))

    if cls and issubclass(cls, CstContainer):
        return cls(children_cst)

    return CstElement(node.type, children_cst)


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
    indent = '  ' * indent_level
    if isinstance(node, CstContainer):
        if isinstance(node, CstElement):
            header = f"{indent}{node.__class__.__name__}(type='{node.node_type}', children=[\n"
        else:
            header = f"{indent}{node.__class__.__name__}([\n"
        children_str = ',\n'.join(pretty_print_cst(c, indent_level + 1) for c in node.children)
        footer = f"\n{indent}])"
        return header + children_str + footer
    elif isinstance(node, CstLeaf):
        return f"{indent}{node.__class__.__name__}({node.text!r})"
    else:
        return f"{indent}{repr(node)}"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file and rebuild it, preserving all formatting."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument("-o", "--output", help="Path to the output file for the rebuilt Nix code")
    args = parser.parse_args()

    parsed_cst = parse_nix_file(Path(args.file))

    if not parsed_cst:
        return

    print("--- Parsed Python Object (CST Representation) ---")
    pretty_cst_string = pretty_print_cst(parsed_cst)
    print(highlight(pretty_cst_string, PythonLexer(), TerminalFormatter()))

    print("\n--- Rebuilt Nix Code ---")
    rebuilt_code = parsed_cst.rebuild()
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))

    if args.output:
        output_path = Path(args.output)
        try:
            output_path.write_text(rebuilt_code, encoding='utf-8')
            print(f"\n--- Rebuilt Nix code written to {output_path} ---")
        except IOError as e:
            print(f"\nError writing to output file {output_path}: {e}")


if __name__ == "__main__":
    main()