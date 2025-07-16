from nix_manipulator.parser import parse


def parse_and_rebuild(source: str):
    parsed_cst = parse(source.encode("utf-8"))
    # print(parsed_cst.model_dump())
    rebuilt_code = parsed_cst.rebuild()
    return rebuilt_code


def test_rebuild_simple_string():
    source = '"hello world"'
    assert source == parse_and_rebuild(source)


def test_rebuild_number():
    source = "123"
    assert source == parse_and_rebuild(source)


def test_rebuild_list():
    source = "[ 1 2 3 ]"
    assert source == parse_and_rebuild(source)


def test_rebuild_set():
    source = "{ a = 1; b = 2; }"
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call():
    source = 'builtins.fetchFromGitHub { name = "foo"; }'
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_arguments():
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  repo = "bar";
  rev = "123";
  sha256 = "abc";
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


# def test_rebuild_function_call_with_multiple_arguments():
#     source = """
# builtins.fetchFromGitHub {
#   owner = "foo";
#   repo = "bar";
#   rev = "123";
#   sha256 = "abc";
# } // {
#   owner = "bar";
#   repo = "baz";
#   rev = "456";
#   sha256 = "def";
# }
# """.strip("\n")
#     assert source == parse_and_rebuild(source)


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


def test_function_definition_empty():
    source = """
{ }: { }
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_function_definition_multiline():
    source = """
{
  a,
}:
{
  b = "hello";
  c = [ a ];
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_function_definition_multiline_longer():
    source = """
{
  arg1,
  arg2,
  arg3,
}:
{
  b = "hello";
  c = [ arg1 ];
  d = 123;
  e = true;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_function_definition_expression():
    source = """
{
  a,
  c,
}:
{
  b = a + 2;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_function_definition_single_line():
    source = """
{ a }: { a = a; b = a; }
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_binary_expression():
    source = "1 + 2"
    assert source == parse_and_rebuild(source)


def test_function_calls_function():
    source = """
{
  a,
  b,
}:
someFunction {
  a = a;
  b = b;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_function_calls_recursive_function():
    source = """
{
  a,
  b,
}:
someFunction rec {
  a = a;
  b = b;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_select():
    source = "foo.bar"
    assert source == parse_and_rebuild(source)


def test_select_three_levels():
    source = "foo.bar.zoo"
    assert source == parse_and_rebuild(source)


def test_nix_with():
    source = "with lib.maintainers; [ hoh ]"
    assert source == parse_and_rebuild(source)


def test_nix_with_multiple_attributes():
    source = "with lib.maintainers; [ hoh mic92 ]"
    assert source == parse_and_rebuild(source)


def test_nix_with_using_selectors():
    source = "with lib.maintainers; [ foo.bar ]"
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_empty_lines_in_argument_set():
    source = """
{

  pkgs,
  # This is a comment

  pkgs-2,

  # Another comment
  pkg-3,

  # A final comment
}:
{
  pkgs = pkgs;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_empty_lines_in_output_set():
    source = """
{
  pkgs,
}:
{
  # Packages
  pkgs = pkgs;

  # Some integers...
  a = 2;
  b = "3";

  # Finishing here.
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_nix_function_calls_a_string():
    source = """
callFunction "with a string"
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_nix_function_calls_a_number():
    source = """
callFunction 32
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_list_multiline():
    source = "[\n  1\n  2\n  true\n  false\n]"
    assert source == parse_and_rebuild(source)


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
  2
  # Comment
  3
]
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_empty_line_before_path():
    source = """
[
  ./ca-load-regression.patch

  # https://seclists.org/fulldisclosure/2025/Jun/2
  ./CVE-2024-47081.patch
]
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_empty_list_assignation():
    source = """
{
  security = [ ];
}
""".strip("\n")
    print(parse(source))
    assert source == parse_and_rebuild(source)


def test_reproduce_plus_plus_function_multiline():
    source = """
[
  # Disable tests that require network access and use httpbin
  "requests.api.request"
]
++ [
  "test_text_response"
]
""".strip("\n")
    print(parse(source))
    assert source == parse_and_rebuild(source)


def test_reproduce_plus_plus_function_call():
    source = """
[
  # Disable tests that require network access and use httpbin
  "requests.api.request"
]
++ lib.optionals (stdenv.hostPlatform.isDarwin && stdenv.hostPlatform.isAarch64) [
  "test_text_response"
]
""".strip("\n")
    print(parse(source))
    assert source == parse_and_rebuild(source)


def test_reproduce_function_call_list_indented():
    source = """
{
  foo = lib.optionals (stdenv.hostPlatform.isDarwin && stdenv.hostPlatform.isAarch64) [
    "test_text_response"
  ];
}
""".strip("\n")
    print(parse(source))
    assert source == parse_and_rebuild(source)


def test_reproduce_let_statement():
    source = """
let
  foo = "bar";
in
foo
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_let_statement_with_comments():
    source = """
let
  foo = "bar";
  # Foo is important
  bar = "baz";
in
foo
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_let_statement_with_comments_and_empty_lines():
    source = """
let

  foo = "bar";

  # Foo is important
  bar = "baz";
in
foo
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert source == parse_and_rebuild(source)


def test_reproduce_indented_string_expression():
    source = """
{
  foo = ''
    hello
    world
  '';
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_parenthesized_string_expression():
    source = """
{
  foo = (''
    hello
    world
  '');
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_parenthesized_function_call():
    source = """
{
  foo = (builtins.fetchFromGitHub {
    owner = "foo";
    repo = "bar";
    rev = "123";
    sha256 = "abc";
  });
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_ellipses():
    source = """
{
  pkgs,
  ...,
}:
{
  pkgs = pkgs;
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source


def test_reproduce_function_takes_identifier():
    source = """
{
  lib,
}:
stdenv.mkDerivation (finalAttrs: {
  pname = "karousel";
})
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert parse_and_rebuild(source) == source
