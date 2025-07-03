from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers.nix import NixLexer

from nix_manipulator.converter import CstToSymbolConverter, parse_nix_cst
from nix_manipulator.parser import pretty_print_cst

# def test_parse_file():
#     source_path = Path(__file__).parent / "nix_files/trl-default-new.nix"
#
#     parsed = convert_nix_file(source_path)
#     print(parsed)
#     assert parsed == nixpkgs_trl_default
#
#
# def test_regenerate():
#     source_path = Path(__file__).parent / "nix_files/trl-default-new.nix"
#
#     parsed = convert_nix_file(source_path)
#     (Path(__file__).parent / "nix_files/trl-default-new-generated-parsed.nix").write_text(parsed.rebuild() + "\n")


def parse_and_rebuild(source: str):
    parsed_cst = parse_nix_cst(source.encode("utf-8"))
    print(pretty_print_cst(parsed_cst))
    converter = CstToSymbolConverter()
    print([converter.convert(parsed_cst)])
    rebuilt_code = parsed_cst.rebuild()
    print(highlight(rebuilt_code, NixLexer(), TerminalFormatter()))
    return rebuilt_code


def test_rebuild_simple_string():
    source = '"hello world"'
    assert source == parse_and_rebuild(source)


def test_rebuild_number():
    source = "123"
    assert source == parse_and_rebuild(source)


# def test_rebuild_list():
#     source = "[1 2 3]"
#     assert source == parse_and_rebuild(source)


def test_rebuild_set():
    source = "{1 2 3}"
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call():
    source = "builtins.fetchFromGitHub { ... }"
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_arguments():
    source = 'builtins.fetchFromGitHub { owner = "foo"; repo = "bar"; rev = "123"; sha256 = "abc"; }'
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_multiple_arguments():
    source = 'builtins.fetchFromGitHub { owner = "foo"; repo = "bar"; rev = "123"; sha256 = "abc"; } // { owner = "bar"; repo = "baz"; rev = "456"; sha256 = "def"; }'
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_multiple_arguments_and_comments():
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  # Comment
  repo = "bar";
  rev = "123";
}
""".strip("\n")
    assert source == parse_and_rebuild(source)
