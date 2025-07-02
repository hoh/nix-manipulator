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

from . import symbols

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

    def as_symbol(self) -> symbols.NixObject:
        """Convert this CST node to a Nix symbol object."""
        raise NotImplementedError(f"Cannot convert {type(self).__name__} to a symbol.")


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

    def as_symbol(self) -> symbols.NixExpression:
        # Fallback: represent this element as a raw expression
        return symbols.NixExpression(value=self.rebuild())


class CstLeaf(CstNode):
    """Base class for leaf nodes in the CST, representing a literal piece of source code."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def __repr__(self):
        return f"{self.__class__.__name__}({self.text.strip()!r})"

    def _rebuild_internal(self) -> str:
        return self.text

    def as_symbol(self) -> symbols.NixExpression:
        # Default leaf -> expression of raw text
        return symbols.NixExpression(value=self.text)


class CstVerbatim(CstLeaf):
    """A generic leaf node for trivia or unknown tokens."""

    pass


# --- Specialized CST classes ---


class NixComment(CstLeaf):
    """A node representing a Nix comment."""

    def as_symbol(self) -> symbols.Comment:
        # Strip leading '#' and whitespace
        text = self.text.lstrip("# ").rstrip("\n")
        return symbols.Comment(text=text)


class NixIdentifier(CstLeaf):
    """A node representing a Nix identifier."""

    def as_symbol(self) -> symbols.NixIdentifier:
        name = self.text.strip()
        return symbols.NixIdentifier(name=name)


class NixString(CstLeaf):
    """A node representing a Nix string."""

    def as_symbol(self) -> symbols.NixExpression:
        # Keep raw string, including quotes
        return symbols.NixExpression(value=self.text)


class NixBinding(CstContainer):
    """A node representing a Nix binding (e.g., `x = 1;`)."""

    def as_symbol(self) -> symbols.NixBinding:
        # Find the identifier and the value node
        name_node = None
        value_node = None
        for child in self.children:
            if isinstance(child, NixIdentifier):
                name_node = child
            # assume non-identifier leaf/container after '=' is the value
            elif hasattr(child, "as_symbol") and not isinstance(child, CstVerbatim):
                try:
                    sym = child.as_symbol()
                except NotImplementedError:
                    continue
                # skip identifier mapping above
                if not isinstance(sym, symbols.NixIdentifier):
                    value_node = child
        if name_node is None or value_node is None:
            raise ValueError(f"Unable to parse binding from CST: {self}")
        return symbols.NixBinding(
            name=name_node.text.strip(), value=value_node.as_symbol()
        )


class NixAttrSet(CstContainer):
    """A node representing a Nix attribute set (e.g., `{ ... }`)."""

    def as_symbol(self) -> symbols.NixAttributeSet:
        bindings = []
        for child in self.children:
            if isinstance(child, NixBinding):
                bindings.append(child.as_symbol())
        return symbols.NixAttributeSet(values=bindings)


class NixLetIn(CstContainer):
    """A node representing a Nix let-in expression."""

    # Fallback to expression
    def as_symbol(self) -> symbols.NixExpression:
        return symbols.NixExpression(value=self.rebuild())


class NixLambda(CstContainer):
    """A node representing a Nix lambda function (e.g., `x: ...`)."""

    def as_symbol(self) -> symbols.FunctionDefinition:
        args = []
        body = None
        for child in self.children:
            if isinstance(child, NixFormal):
                args.append(child.as_symbol())
            elif hasattr(child, "as_symbol") and not isinstance(
                child, (NixFormal, CstVerbatim)
            ):
                # first non-formal is body
                if body is None:
                    body = child.as_symbol()
        return symbols.FunctionDefinition(
            argument_set=args, let_statements=[], result=body
        )


class NixFormal(CstContainer):
    """A node representing a formal parameter in a lambda."""

    @property
    def identifier(self) -> Optional[NixIdentifier]:
        """Returns the identifier of the formal parameter, if found."""
        for child in self.children:
            if isinstance(child, NixIdentifier):
                return child
        return None

    def as_symbol(self) -> symbols.NixIdentifier:
        ident = self.identifier
        if not ident:
            raise ValueError(f"Formal parameter without identifier: {self}")
        return symbols.NixIdentifier(name=ident.text.strip())


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
        base_repr += f", post_trivia=[...{node.post_trivia} item(s)]"

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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse a Nix file and rebuild it, preserving all formatting."
    )
    parser.add_argument("file", help="Path to the Nix file to process")
    parser.add_argument(
        "-o", "--output", help="Path to the output file for the rebuilt Nix code"
    )
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
            output_path.write_text(rebuilt_code, encoding="utf-8")
            print(f"\n--- Rebuilt Nix code written to {output_path} ---")
        except IOError as e:
            print(f"\nError writing to output file {output_path}: {e}")


if __name__ == "__main__":
    main()
