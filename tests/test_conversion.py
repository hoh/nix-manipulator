from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer

from nix_manipulator.converter import CstToSymbolConverter
from nix_manipulator.cst.parser import parse_nix_cst
from nix_manipulator.cst.utils import pretty_print_cst


def parse_and_rebuild(source: str):
    parsed_cst = parse_nix_cst(source.encode("utf-8"))
    print(pretty_print_cst(parsed_cst))
    converter = CstToSymbolConverter()
    print([converter.convert(parsed_cst)])
    print(parsed_cst)
    rebuilt_code = parsed_cst.rebuild()
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))
    return rebuilt_code


def test_rebuild_simple_string():
    source = '"hello world"'
    assert source == parse_and_rebuild(source)


def test_rebuild_number():
    source = "123"
    assert source == parse_and_rebuild(source)


def test_rebuild_list():
    source = "[\n  1\n  2\n  3\n]"
    assert source == parse_and_rebuild(source)


# def test_rebuild_set():
#     source = '{ a: "b"; }'
#     assert source == parse_and_rebuild(source)


def test_rebuild_function_call():
    source = "builtins.fetchFromGitHub {\n  a = 2;\n}"
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_arguments():
    source = (
        'builtins.fetchFromGitHub {\n  owner = "foo";\n  repo = "bar";\n  rev = 123;\n}'
    )
    assert source == parse_and_rebuild(source)



# def test_rebuild_function_call_with_multiple_arguments():
#     source = 'builtins.fetchFromGitHub { owner = "foo"; repo = "bar"; rev = "123"; sha256 = "abc"; } // { owner = "bar"; repo = "baz"; rev = "456"; sha256 = "def"; }'
#     assert source == parse_and_rebuild(source)

def test_rebuild_function_call_with_comment():
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  # Comment
  repo = "bar";
  rev = "123";
}
""".strip("\n")
    assert source == parse_and_rebuild(source)

def test_rebuild_list_with_comment():
    source = """
[
    1
    true
    3
]
""".strip("\n")
    assert source == parse_and_rebuild(source)
