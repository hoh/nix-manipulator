from nix_manipulator.parser import parse
from tests.nixfmt_helpers import validate_nixfmt_rfc


def parse_and_rebuild(source: str):
    """Why: lock in parse and rebuild behavior to prevent regressions."""
    parsed_cst = parse(source.encode("utf-8"))
    # print(parsed_cst.model_dump())
    rebuilt_code = parsed_cst.rebuild()
    return rebuilt_code


def test_rebuild_simple_string():
    """Why: lock in rebuild simple string behavior to prevent regressions."""
    source = '"hello world"'
    assert source == parse_and_rebuild(source)


def test_rebuild_number():
    """Why: lock in rebuild number behavior to prevent regressions."""
    source = "123"
    assert source == parse_and_rebuild(source)


def test_rebuild_list():
    """Why: lock in rebuild list behavior to prevent regressions."""
    source = "[ 1 2 3 ]"
    assert source == parse_and_rebuild(source)


def test_rebuild_set():
    """Why: lock in rebuild set behavior to prevent regressions."""
    source = "{ a = 1; b = 2; }"
    assert source == parse_and_rebuild(source)


def test_normalize_binding_semicolon_spacing():
    """Why: normalize binding semicolon spacing to the RFC-style form."""
    source = "{ foo = bar ; }"
    expected = validate_nixfmt_rfc("{ foo = bar; }")
    assert parse_and_rebuild(source) == expected


def test_normalize_function_definition_colon_spacing():
    """Why: attach function definition colons to their arguments."""
    source = "{ pkgs } : pkgs.hello"
    expected = validate_nixfmt_rfc("{ pkgs }: pkgs.hello")
    assert parse_and_rebuild(source) == expected


def test_normalize_unary_operator_spacing():
    """Why: normalize unary operators to attach to their operands."""
    source = """
{
  x = ! x;
  y = - x;
  z = ! (foo bar);
  a = - (x + y);
  b = - 1;
}
""".strip("\n")
    expected = validate_nixfmt_rfc(
        """
{
  x = !x;
  y = -x;
  z = !(foo bar);
  a = -(x + y);
  b = -1;
}
""".strip("\n")
    )
    assert parse_and_rebuild(source) == expected


def test_rebuild_nested_set():
    """Why: lock in rebuild nested set behavior to prevent regressions."""
    source = "{ a.b = 1; a.c = 2; }"
    assert source == parse_and_rebuild(source)


def test_rebuild_explicit_nested_set():
    source = """
{
  a = {
    b = 1;
    c = 2;
  };
}
""".strip("\n")
    assert source == parse_and_rebuild(source)

def test_rebuild_invalid_nested_combination():
    """Attrpath and explicit attrsets are merged when both are attribute sets."""
    source = """
{
  a.b = 1;
  a.c = 2;

  a = {
    d = 3;
  };
}
""".strip("\n")
    assert source == parse_and_rebuild(source)

def test_rebuild_multi_level_nested_set():
    source = """
{
  a = {
    b = 1;
    c = 2;
    d = {
      e = 3;
    };
    f.g = 4;
  };
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_multi_level_nested_set_alternative():
    source = """
{
  a = {
    b = 1;
    c = 2;
    d.e = 3;
    f = {
      g = 4;
    };
  };
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call():
    """Why: lock in rebuild function call behavior to prevent regressions."""
    source = 'builtins.fetchFromGitHub { name = "foo"; }'
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_arguments():
    """Why: lock in rebuild function call with arguments behavior to prevent regressions."""
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  repo = "bar";
  rev = "123";
  sha256 = "abc";
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
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
    """Why: lock in rebuild function call with multiple arguments and comments behavior to prevent regressions."""
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  # Comment
  repo = "bar";
  rev = "123";
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_definition_empty():
    """Why: lock in function definition empty behavior to prevent regressions."""
    source = """
{ }: { }
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_definition_multiline():
    """Why: lock in function definition multiline behavior to prevent regressions."""
    source = """
{ a }:
{
  b = "hello";
  c = [ a ];
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_definition_multiline_longer():
    """Why: lock in function definition multiline longer behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_definition_expression():
    """Why: lock in function definition expression behavior to prevent regressions."""
    source = """
{ a, c }:
{
  b = a + 2;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_definition_single_line():
    """Why: lock in function definition single line behavior to prevent regressions."""
    source = """
{ a }:
{
  a = a;
  b = a;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_binary_expression():
    """Why: lock in binary expression behavior to prevent regressions."""
    source = "1 + 2"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_calls_function():
    """Why: lock in function calls function behavior to prevent regressions."""
    source = """
{ a, b }:
someFunction {
  a = a;
  b = b;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_function_calls_recursive_function():
    """Why: lock in function calls recursive function behavior to prevent regressions."""
    source = """
{ a, b }:
someFunction rec {
  a = a;
  b = b;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_select():
    """Why: lock in select behavior to prevent regressions."""
    source = "foo.bar"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_select_three_levels():
    """Why: lock in select three levels behavior to prevent regressions."""
    source = "foo.bar.zoo"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_select_default_inline_comment():
    """Why: lock in select default inline comment behavior to prevent regressions."""
    source = "foo.bar # comment\n  or baz"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_select_comment_between_expression_and_attrpath():
    """Why: preserve comments between a selector base and its attrpath."""
    source = """
{
  value =
    ({ foo = "bar"; })
    # keep this comment
    .foo;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_with():
    """Why: lock in nix with behavior to prevent regressions."""
    source = "with lib.maintainers; [ hoh ]"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_with_multiple_attributes():
    """Why: lock in nix with multiple attributes behavior to prevent regressions."""
    source = "with lib.maintainers;\n[\n  hoh\n  mic92\n]"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_with_using_selectors():
    """Why: lock in nix with using selectors behavior to prevent regressions."""
    source = "with lib.maintainers; [ foo.bar ]"
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_with_comment_after_semicolon():
    """Why: keep `with` comments from collapsing body indentation."""
    source = """
{
  foo =
    with pkgs; # keep this comment
    bar;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_with_comment_between_with_and_env():
    """Why: preserve comments between `with` and the environment expression."""
    source = """
{
  foo =
    with # keep this comment
      pkgs;
    bar;
}
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_empty_lines_in_argument_set():
    """Why: lock in nix function definition empty lines in argument set behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_comment_before_colon():
    """Why: preserve comments between function args and the colon."""
    source = """
{ foo } # keep
: foo
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_inline_comment_before_colon():
    """Why: keep inline block comments before the colon on the same line."""
    source = "{ foo } /* keep */ : foo"
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_empty_formals_with_comment():
    """Why: keep comments inside empty formals without crashing rebuilds."""
    source = """
{
# no arguments
}:
{ }
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_function_definition_empty_lines_in_output_set():
    """Why: lock in nix function definition empty lines in output set behavior to prevent regressions."""
    source = """
{ pkgs }:
{
  # Packages
  pkgs = pkgs;

  # Some integers...
  a = 2;
  b = "3";

  # Finishing here.
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_function_calls_a_string():
    """Why: lock in nix function calls a string behavior to prevent regressions."""
    source = """
callFunction "with a string"
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_nix_function_calls_a_number():
    """Why: lock in nix function calls a number behavior to prevent regressions."""
    source = """
callFunction 32
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_rebuild_list_multiline():
    """Why: lock in rebuild list multiline behavior to prevent regressions."""
    source = "[\n  1\n  2\n  true\n  false\n]"
    assert source == parse_and_rebuild(source)


def test_unary_comment_between_operator_and_operand():
    """Why: keep comments between unary operators and their operands."""
    source = """
! # guard
  foo
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_if_else_inline_comment():
    """Why: preserve inline comments after else."""
    source = """
if cond then
  foo
else # note
  bar
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_has_attr_comments_around_question_mark():
    """Why: preserve comments around the `?` operator."""
    source = """
foo # left
? # right
  bar
""".strip("\n")
    assert source == parse_and_rebuild(source)


def test_rebuild_function_call_with_comment():
    """Why: lock in rebuild function call with comment behavior to prevent regressions."""
    source = """
builtins.fetchFromGitHub {
  owner = "foo";
  # Comment
  repo = "bar";
  rev = "123";
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_rebuild_list_with_comment():
    """Why: lock in rebuild list with comment behavior to prevent regressions."""
    source = """
[
  1
  2
  # Comment
  3
]
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_rebuild_empty_line_before_path():
    """Why: lock in rebuild empty line before path behavior to prevent regressions."""
    source = """
[
  ./ca-load-regression.patch

  # https://seclists.org/fulldisclosure/2025/Jun/2
  ./CVE-2024-47081.patch
]
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_rebuild_empty_list_assignation():
    """Why: lock in rebuild empty list assignation behavior to prevent regressions."""
    source = "{ security = [ ]; }"
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_reproduce_comment_before_operator():
    """Why: lock in reproduce comment before operator behavior to prevent regressions."""
    source = """
{
  foo = [
    1
  ]
  # Comment
  ++ bar;
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_binary_comment_between_operator_and_operand():
    """Why: preserve comments between a binary operator and RHS."""
    source = """
{
  value =
    left ==
    # Comment about the rhs
    right;
}
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_plus_plus_function_multiline():
    """Why: lock in reproduce plus plus function multiline behavior to prevent regressions."""
    source = """
[
  # Disable tests that require network access and use httpbin
  "requests.api.request"
]
++ [ "test_text_response" ]
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_reproduce_plus_plus_function_call():
    """Why: lock in reproduce plus plus function call behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_reproduce_function_call_list_indented():
    """Why: lock in reproduce function call list indented behavior to prevent regressions."""
    source = """
{
  foo = lib.optionals (stdenv.hostPlatform.isDarwin && stdenv.hostPlatform.isAarch64) [
    "test_text_response"
  ];
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_reproduce_let_statement():
    """Why: lock in reproduce let statement behavior to prevent regressions."""
    source = """
let
  foo = "bar";
in
foo
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_let_statement_trailing_comment():
    """Why: preserve trailing body comments inside let expressions."""
    source = """
let
  foo = "bar";
in
foo # trailing
""".strip("\n")
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_let_statement_with_comments():
    """Why: lock in reproduce let statement with comments behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_let_statement_with_comments_and_empty_lines():
    """Why: lock in reproduce let statement with comments and empty lines behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert source == parse_and_rebuild(source)


def test_reproduce_indented_string_expression():
    """Why: lock in reproduce indented string expression behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_parenthesized_string_expression():
    """Why: lock in reproduce parenthesized string expression behavior to prevent regressions."""
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
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_parenthesized_function_call():
    """Why: lock in reproduce parenthesized function call behavior to prevent regressions."""
    source = """
{
  foo = (
    builtins.fetchFromGitHub {
      owner = "foo";
      repo = "bar";
      rev = "123";
      sha256 = "abc";
    }
  );
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_ellipses():
    """Why: lock in reproduce ellipses behavior to prevent regressions."""
    source = """
{ pkgs, ... }:
{
  pkgs = pkgs;
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_function_takes_identifier():
    """Why: lock in reproduce function takes identifier behavior to prevent regressions."""
    source = """
{ lib }:
stdenv.mkDerivation (finalAttrs: {
  pname = "karousel";
})
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_reproduce_optional_arguments():
    """Why: lock in reproduce optional arguments behavior to prevent regressions."""
    source = """
{
  system ? builtins.currentSystem,
}:
pkgs.callPackage (
  {
    gh,
    importNpmLock,
    mkShell,
    nodejs,
  }:
  mkShell {
    packages = [ nodejs ];

    npmDeps = importNpmLock.buildNodeModules {
      npmRoot = ./.;
      inherit nodejs;
    };
  }
) { }
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_function_call_outputs_with_expression():
    """Why: lock in function call outputs with expression behavior to prevent regressions."""
    source = """
{ lib }:
mkKdeDerivation {
  extraNativeBuildInputs = [
    kpackage
    pkg-config
    (python3.withPackages (ps: with ps; [ websockets ]))
  ];
}
""".strip("\n")
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_function_call_outputs_function_expression():
    """Why: lock in function call outputs function expression behavior to prevent regressions."""
    source = "{ }: { a }: a"
    print(parse(source))
    print(parse_and_rebuild(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_assert_expression():
    """Why: lock in assert expression behavior to prevent regressions."""
    source = """
{ lib, stdenv }:

assert stdenv.buildPlatform.system == "x86_64-linux";

{
  a = 2;
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_assert_comment_after_assert():
    """Why: preserve comments between `assert` and its condition."""
    source = """
assert # guard comment
  foo == bar;
true
""".strip("\n")
    assert parse_and_rebuild(source) == source


def test_assert_comment_before_semicolon():
    """Why: preserve comments between the condition and `;`."""
    source = """
assert foo == bar
# guard comment
;
true
""".strip("\n")
    assert parse_and_rebuild(source) == source


def test_unary_expression():
    """Why: lock in unary expression behavior to prevent regressions."""
    source = "!foo"
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_complex_expression():
    """Why: lock in complex expression behavior to prevent regressions."""
    source = """
(!blas.isILP64) && (!lapack.isILP64)
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert [parse_and_rebuild(source)] == [source]


def test_inherit_from():
    """Why: lock in inherit from behavior to prevent regressions."""
    source = """
{ emulator, rom }:

symlinkJoin {
  inherit (emulator) version;

  paths = [
    emulator
    rom
    runScript
  ];
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_inherit_quoted_names():
    """Why: lock in inherit quoted names behavior to prevent regressions."""
    source = '{ inherit "foo" "bar"; }'
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_comment_in_let():
    """Why: lock in rebuild comment in let behavior to prevent regressions."""
    source = """
{ lib }:

let
  # Some comment
  key = 3;
in
{ }
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_if_statement():
    """Why: lock in rebuild if statement behavior to prevent regressions."""
    source = "if 1 == 1 then 2 else 3"
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_binding_to_if_statement():
    """Why: lock in rebuild binding to if statement behavior to prevent regressions."""
    source = "{ a = if true then 2 else 3; }"
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_binding_to_list():
    """Why: lock in rebuild binding to list behavior to prevent regressions."""
    source = """
{
  a = [
    1
    2
    3
  ];
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_function_arg_list():
    """Why: lock in rebuild function arg list behavior to prevent regressions."""
    source = """
{
  extensions ? exts: [ ],
}:
{ }
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_complex_string():
    """Why: lock in rebuild complex string behavior to prevent regressions."""
    source = '"--with-pinentry-pgm=${pinentry}/${pinentry.binaryPath or "bin/pinentry"}"'
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_function_arguments_at():
    """Why: lock in rebuild function arguments at behavior to prevent regressions."""
    source = """
{ callPackage, python3, ... }@args:

{ }
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_function_arguments_at_reversed():
    """Why: lock in rebuild function arguments at reversed behavior to prevent regressions."""
    source = """
args@{ callPackage, python3, ... }:

{ }
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_indentation_with_binary_chainable_operator():
    """This code was adjusted from nixpkgs to be RFC-0166 compliant
    pkgs/tools/package-management/nix/modular/packaging/components.nix
    """
    source = """
{
  setVersionLayer = finalAttrs: prevAttrs: {
    preConfigure =
      prevAttrs.preConfigure or ""
      +
        # Update the repo-global .version file.
        # Symlink ./.version points there, but by default only workDir is writable.
        ''
          chmod u+w ./.version
          echo ${finalAttrs.version} > ./.version
        '';
  };
}
""".strip("\n")
    print(parse(source))
    # assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_indentation_with_implication_operator():
    """Ensure RFC indentation for implication chains with && operands."""
    source = """
{
  value =
    stdenv.hostPlatform.isAarch
    ->
      stdenv.hostPlatform.parsed.cpu ? version
      && lib.versionAtLeast stdenv.hostPlatform.parsed.cpu.version "6";
}
""".strip("\n")
    print(parse(source))
    assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) == source


def test_rebuild_indentation_with_binary_chainable_operator_invalid_indentation():
    """This code found in nixpkgs is not RFC-0166 compliant but nixfmt formats it like this
    pkgs/tools/package-management/nix/modular/packaging/components.nix
    """
    source = """
{
  setVersionLayer = finalAttrs: prevAttrs: {
    preConfigure =
      prevAttrs.preConfigure or ""
      +
      # Update the repo-global .version file.
      # Symlink ./.version points there, but by default only workDir is writable.
      ''
        chmod u+w ./.version
        echo ${finalAttrs.version} > ./.version
      '';
  };
}
""".strip("\n")
    print(parse(source))
    # assert validate_nixfmt_rfc(source)
    assert parse_and_rebuild(source) != source
