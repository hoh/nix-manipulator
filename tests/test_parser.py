import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import tempfile

from nix_manipulator.parser import (
    extract_text,
    CstNode,
    CstContainer,
    CstElement,
    CstLeaf,
    CstVerbatim,
    NixComment,
    NixIdentifier,
    NixString,
    NixBinding,
    NixAttrSet,
    NixLetIn,
    NixLambda,
    NixFormal,
    NODE_TYPE_TO_CLASS,
    parse_to_cst,
    parse_nix_cst,
    parse_nix_file,
    pretty_print_cst,
)


class TestExtractText:
    """Test the extract_text utility function."""

    def test_extract_text_basic(self):
        """Test basic text extraction from a node."""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        code = b"hello world"

        result = extract_text(mock_node, code)
        assert result == "hello"

    def test_extract_text_middle(self):
        """Test text extraction from middle of code."""
        mock_node = Mock()
        mock_node.start_byte = 6
        mock_node.end_byte = 11
        code = b"hello world"

        result = extract_text(mock_node, code)
        assert result == "world"

    def test_extract_text_empty(self):
        """Test text extraction with empty range."""
        mock_node = Mock()
        mock_node.start_byte = 5
        mock_node.end_byte = 5
        code = b"hello world"

        result = extract_text(mock_node, code)
        assert result == ""


class TestCstNode:
    """Test the base CstNode class."""

    def test_cst_node_init(self):
        """Test CstNode initialization."""
        node = CstNode()
        assert node.post_trivia == []

    def test_cst_node_rebuild_not_implemented(self):
        """Test that _rebuild_internal raises NotImplementedError."""
        node = CstNode()
        with pytest.raises(NotImplementedError):
            node._rebuild_internal()

    def test_cst_node_rebuild_with_trivia(self):
        """Test rebuild method with post trivia."""
        node = CstLeaf("test")
        trivia = CstVerbatim(" ")
        node.post_trivia = [trivia]

        result = node.rebuild()
        assert result == "test "


class TestCstContainer:
    """Test the CstContainer class."""

    def test_cst_container_init(self):
        """Test CstContainer initialization."""
        children = [CstLeaf("a"), CstLeaf("b")]
        container = CstContainer(children)

        assert container.children == children
        assert container.post_trivia == []

    def test_cst_container_rebuild(self):
        """Test CstContainer rebuild method."""
        children = [CstLeaf("hello"), CstLeaf(" "), CstLeaf("world")]
        container = CstContainer(children)

        result = container.rebuild()
        assert result == "hello world"

    def test_cst_container_repr(self):
        """Test CstContainer string representation."""
        children = [CstLeaf("test")]
        container = CstContainer(children)

        result = repr(container)
        assert "CstContainer(children=[...])" == result


class TestCstElement:
    """Test the CstElement class."""

    def test_cst_element_init(self):
        """Test CstElement initialization."""
        children = [CstLeaf("test")]
        element = CstElement("identifier", children)

        assert element.node_type == "identifier"
        assert element.children == children

    def test_cst_element_repr(self):
        """Test CstElement string representation."""
        children = [CstLeaf("test")]
        element = CstElement("identifier", children)

        result = repr(element)
        assert "CstElement(type='identifier', children=[...])" == result


class TestCstLeaf:
    """Test the CstLeaf class."""

    def test_cst_leaf_init(self):
        """Test CstLeaf initialization."""
        leaf = CstLeaf("hello")
        assert leaf.text == "hello"
        assert leaf.post_trivia == []

    def test_cst_leaf_rebuild(self):
        """Test CstLeaf rebuild method."""
        leaf = CstLeaf("hello")
        assert leaf.rebuild() == "hello"

    def test_cst_leaf_repr(self):
        """Test CstLeaf string representation."""
        leaf = CstLeaf("  hello  ")
        result = repr(leaf)
        assert "CstLeaf('hello')" == result


class TestSpecializedClasses:
    """Test specialized CST classes."""

    def test_nix_comment(self):
        """Test NixComment class."""
        comment = NixComment("# This is a comment")
        assert comment.text == "# This is a comment"
        assert isinstance(comment, CstLeaf)

    def test_nix_identifier(self):
        """Test NixIdentifier class."""
        identifier = NixIdentifier("myVar")
        assert identifier.text == "myVar"
        assert isinstance(identifier, CstLeaf)

    def test_nix_string(self):
        """Test NixString class."""
        string = NixString('"hello world"')
        assert string.text == '"hello world"'
        assert isinstance(string, CstLeaf)

    def test_nix_binding(self):
        """Test NixBinding class."""
        children = [NixIdentifier("x"), CstVerbatim(" = "), CstLeaf("1")]
        binding = NixBinding(children)
        assert isinstance(binding, CstContainer)
        assert binding.children == children

    def test_nix_attr_set(self):
        """Test NixAttrSet class."""
        children = [CstVerbatim("{ "), NixIdentifier("x"), CstVerbatim(" }")]
        attr_set = NixAttrSet(children)
        assert isinstance(attr_set, CstContainer)
        assert attr_set.children == children

    def test_nix_let_in(self):
        """Test NixLetIn class."""
        children = [CstVerbatim("let "), NixIdentifier("x"), CstVerbatim(" in")]
        let_in = NixLetIn(children)
        assert isinstance(let_in, CstContainer)
        assert let_in.children == children

    def test_nix_lambda(self):
        """Test NixLambda class."""
        children = [NixIdentifier("x"), CstVerbatim(": "), NixIdentifier("x")]
        lambda_node = NixLambda(children)
        assert isinstance(lambda_node, CstContainer)
        assert lambda_node.children == children


class TestNixFormal:
    """Test the NixFormal class."""

    def test_nix_formal_with_identifier(self):
        """Test NixFormal with an identifier."""
        identifier = NixIdentifier("param")
        children = [identifier, CstVerbatim(" ? "), CstLeaf("default")]
        formal = NixFormal(children)

        assert formal.identifier == identifier

    def test_nix_formal_without_identifier(self):
        """Test NixFormal without an identifier."""
        children = [CstVerbatim("...")]
        formal = NixFormal(children)

        assert formal.identifier is None

    def test_nix_formal_multiple_identifiers(self):
        """Test NixFormal with multiple identifiers (returns first)."""
        id1 = NixIdentifier("param1")
        id2 = NixIdentifier("param2")
        children = [id1, CstVerbatim(", "), id2]
        formal = NixFormal(children)

        assert formal.identifier == id1


class TestNodeTypeToClass:
    """Test the NODE_TYPE_TO_CLASS mapping."""

    def test_node_type_mapping(self):
        """Test that all expected node types are mapped correctly."""
        expected_mappings = {
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

        assert NODE_TYPE_TO_CLASS == expected_mappings


class TestParsingFunctions:
    """Test the main parsing functions."""

    @patch('nix_manipulator.parser.PARSER')
    def test_parse_nix_cst(self, mock_parser):
        """Test parse_nix_cst function."""
        # Mock the tree-sitter parser
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.type = "source_code"
        mock_root.children = []
        mock_root.start_byte = 0
        mock_root.end_byte = 4
        mock_tree.root_node = mock_root
        mock_parser.parse.return_value = mock_tree

        source_code = b"test"

        with patch('nix_manipulator.parser.parse_to_cst') as mock_parse_to_cst:
            mock_parse_to_cst.return_value = CstVerbatim("test")
            result = parse_nix_cst(source_code)

            mock_parser.parse.assert_called_once_with(source_code)
            mock_parse_to_cst.assert_called_once_with(mock_root, source_code)
            assert isinstance(result, CstVerbatim)

    def test_parse_nix_file_success(self):
        """Test successful file parsing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.nix', delete=False) as f:
            f.write('{ hello = "world"; }')
            temp_path = Path(f.name)

        try:
            with patch('nix_manipulator.parser.parse_nix_cst') as mock_parse:
                mock_parse.return_value = CstVerbatim("test")
                result = parse_nix_file(temp_path)

                assert result is not None
                mock_parse.assert_called_once()
        finally:
            temp_path.unlink()

    def test_parse_nix_file_not_found(self):
        """Test file parsing with non-existent file."""
        non_existent_path = Path("/non/existent/file.nix")

        with patch('builtins.print') as mock_print:
            result = parse_nix_file(non_existent_path)

            assert result is None
            mock_print.assert_called_once()
            assert "Error parsing file" in mock_print.call_args[0][0]

    def test_parse_nix_file_read_error(self):
        """Test file parsing with read error."""
        with tempfile.NamedTemporaryFile(suffix='.nix', delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Delete the file to cause a read error
            temp_path.unlink()

            with patch('builtins.print') as mock_print:
                result = parse_nix_file(temp_path)

                assert result is None
                mock_print.assert_called_once()
                assert "Error parsing file" in mock_print.call_args[0][0]
        except FileNotFoundError:
            pass  # File already deleted


class TestParseToCST:
    """Test the parse_to_cst function."""

    def test_parse_leaf_node_with_specialized_class(self):
        """Test parsing a leaf node with a specialized class."""
        mock_node = Mock()
        mock_node.type = "comment"
        mock_node.children = []
        mock_node.start_byte = 0
        mock_node.end_byte = 12
        code = b"# comment"

        with patch('nix_manipulator.parser.extract_text', return_value="# comment"):
            result = parse_to_cst(mock_node, code)

            assert isinstance(result, NixComment)
            assert result.text == "# comment"

    def test_parse_leaf_node_without_specialized_class(self):
        """Test parsing a leaf node without a specialized class."""
        mock_node = Mock()
        mock_node.type = "unknown_type"
        mock_node.children = []
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        code = b"test"

        with patch('nix_manipulator.parser.extract_text', return_value="test"):
            result = parse_to_cst(mock_node, code)

            assert isinstance(result, CstVerbatim)
            assert result.text == "test"

    def test_parse_container_node_with_specialized_class(self):
        """Test parsing a container node with specialized class."""
        # Create mock child node
        mock_child = Mock()
        mock_child.type = "identifier"
        mock_child.children = []
        mock_child.start_byte = 2
        mock_child.end_byte = 3

        # Create mock parent node
        mock_node = Mock()
        mock_node.type = "binding"
        mock_node.children = [mock_child]
        mock_node.start_byte = 0
        mock_node.end_byte = 5

        code = b"{ x }"

        with patch('nix_manipulator.parser.extract_text') as mock_extract:
            mock_extract.side_effect = lambda n, c: {
                mock_child: "x"
            }.get(n, "")

            result = parse_to_cst(mock_node, code)

            assert isinstance(result, NixBinding)
            assert len(result.children) >= 1

    def test_parse_container_node_without_specialized_class(self):
        """Test parsing a container node without specialized class."""
        # Create mock child node
        mock_child = Mock()
        mock_child.type = "identifier"
        mock_child.children = []
        mock_child.start_byte = 0
        mock_child.end_byte = 4

        # Create mock parent node
        mock_node = Mock()
        mock_node.type = "unknown_container"
        mock_node.children = [mock_child]
        mock_node.start_byte = 0
        mock_node.end_byte = 4

        code = b"test"

        with patch('nix_manipulator.parser.extract_text', return_value="test"):
            result = parse_to_cst(mock_node, code)

            assert isinstance(result, CstElement)
            assert result.node_type == "unknown_container"

    def test_parse_with_trivia_attachment(self):
        """Test that trivia is properly attached to nodes."""
        # Create mock child nodes
        mock_child1 = Mock()
        mock_child1.type = "identifier"
        mock_child1.children = []
        mock_child1.start_byte = 0
        mock_child1.end_byte = 1

        mock_child2 = Mock()
        mock_child2.type = "identifier"
        mock_child2.children = []
        mock_child2.start_byte = 3
        mock_child2.end_byte = 4

        # Create mock parent node with space between children
        mock_node = Mock()
        mock_node.type = "test_container"
        mock_node.children = [mock_child1, mock_child2]
        mock_node.start_byte = 0
        mock_node.end_byte = 4

        code = b"x y"  # 'x' at 0-1, space at 1-3, 'y' at 3-4

        with patch('nix_manipulator.parser.extract_text') as mock_extract:
            def extract_side_effect(node, code_bytes):
                if node == mock_child1:
                    return "x"
                elif node == mock_child2:
                    return "y"
                return ""

            mock_extract.side_effect = extract_side_effect

            result = parse_to_cst(mock_node, code)

            assert isinstance(result, CstElement)
            # First child should have trivia attached (the space and second identifier)
            assert len(result.children) >= 1
            first_child = result.children[0]
            # The space between identifiers should be attached as trivia
            assert len(first_child.post_trivia) > 0


class TestPrettyPrintCST:
    """Test the pretty_print_cst function."""

    def test_pretty_print_leaf(self):
        """Test pretty printing a leaf node."""
        leaf = CstLeaf("hello")
        result = pretty_print_cst(leaf)

        assert "CstLeaf('hello')" in result

    def test_pretty_print_element(self):
        """Test pretty printing an element node."""
        element = CstElement("identifier", [CstLeaf("test")])
        result = pretty_print_cst(element)

        assert "CstElement(type='identifier'" in result
        assert "children=[" in result

    def test_pretty_print_container(self):
        """Test pretty printing a container node."""
        children = [CstLeaf("a"), CstLeaf("b")]
        container = CstContainer(children)
        result = pretty_print_cst(container)

        assert "CstContainer(" in result
        assert "children=[" in result
        assert "CstLeaf('a')" in result
        assert "CstLeaf('b')" in result

    def test_pretty_print_with_trivia(self):
        """Test pretty printing with post trivia."""
        leaf = CstLeaf("test")
        leaf.post_trivia = [CstVerbatim(" "), CstVerbatim(",")]
        result = pretty_print_cst(leaf)

        assert "post_trivia=[...2 item(s)]" in result

    def test_pretty_print_nested_containers(self):
        """Test pretty printing with nested containers."""
        inner_container = CstContainer([CstLeaf("inner")])
        outer_container = CstContainer([inner_container, CstLeaf("outer")])
        result = pretty_print_cst(outer_container)

        assert "CstContainer(" in result
        assert "CstLeaf('inner')" in result
        assert "CstLeaf('outer')" in result

    def test_pretty_print_with_indentation(self):
        """Test pretty printing with custom indentation."""
        leaf = CstLeaf("test")
        result = pretty_print_cst(leaf, indent_level=2)

        # Should start with 4 spaces (2 levels * 2 spaces each)
        assert result.startswith("    ")


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_rebuild_preserves_source(self):
        """Test that rebuilding a CST preserves the original source."""
        # Create a simple CST structure
        children = [
            NixIdentifier("hello"),
            CstVerbatim(" = "),
            NixString('"world"'),
            CstVerbatim(";")
        ]
        binding = NixBinding(children)

        result = binding.rebuild()
        assert result == 'hello = "world";'

    def test_trivia_preservation(self):
        """Test that trivia is preserved through parsing and rebuilding."""
        # Create a node with post trivia
        identifier = NixIdentifier("test")
        identifier.post_trivia = [
            CstVerbatim(" "),
            NixComment("# comment"),
            CstVerbatim("\n")
        ]

        result = identifier.rebuild()
        assert result == "test # comment\n"

    def test_complex_nesting(self):
        """Test complex nested structures."""
        # Create nested attribute set
        inner_binding = NixBinding([
            NixIdentifier("inner"),
            CstVerbatim(" = "),
            NixString('"value"')
        ])

        attr_set = NixAttrSet([
            CstVerbatim("{ "),
            inner_binding,
            CstVerbatim(" }")
        ])

        outer_binding = NixBinding([
            NixIdentifier("outer"),
            CstVerbatim(" = "),
            attr_set
        ])

        result = outer_binding.rebuild()
        assert result == 'outer = { inner = "value" }'


if __name__ == "__main__":
    pytest.main([__file__])