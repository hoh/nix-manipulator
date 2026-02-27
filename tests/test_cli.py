from pathlib import Path
from textwrap import dedent

from nix_manipulator.__main__ import main
from tests.internal.cli.helpers import transform_with_cli


def test_cli_set_boolean(capsys):
    """Guard CLI boolean updates to ensure user edits stay stable."""
    result = main(
        ["set", "-f", "tests/nix-files/pkgs/simplistic-01.nix", "doCheck", "true"]
    )
    out = capsys.readouterr().out.rstrip("\n")
    original = Path("tests/nix-files/pkgs/simplistic-01.nix").read_text().strip("\n")
    assert result == 0
    assert out == original.replace("doCheck = false;", "doCheck = true;")


def test_cli_set_string(capsys):
    """Guard CLI string updates so version changes remain predictable."""
    result = main(
        ["set", "-f", "tests/nix-files/pkgs/simplistic-01.nix", "version", '"1.2.3"']
    )
    out = capsys.readouterr().out.rstrip("\n")
    original = Path("tests/nix-files/pkgs/simplistic-01.nix").read_text().strip("\n")
    assert result == 0
    assert out == original.replace('version = "0.15.2";', 'version = "1.2.3";')


def test_cli_rm(capsys):
    """Guard CLI deletions so removal logic preserves surrounding layout."""
    result = main(["rm", "-f", "tests/nix-files/pkgs/simplistic-01.nix", "doCheck"])
    out = capsys.readouterr().out.rstrip("\n")
    original = Path("tests/nix-files/pkgs/simplistic-01.nix").read_text().strip("\n")
    assert result == 0
    assert out == original.replace(
        "# Many tests require internet access.\n  doCheck = false;\n\n  ", ""
    )


def test_cli_test(capsys):
    """Guard CLI round-trip checks to signal formatting drift."""
    result = main(["test", "-f", "tests/nix-files/pkgs/simplistic-01.nix"])
    out = capsys.readouterr().out.rstrip("\n")
    assert result == 0
    assert out == "OK"


def test_cli_test_mismatch_exit_code(tmp_path, capsys):
    """Ensure round-trip mismatches return a failing exit code."""
    path = tmp_path / "non-rfc.nix"
    path.write_text("{foo=1;}", encoding="utf-8")
    result = main(["test", "-f", str(path)])
    out = capsys.readouterr().out.rstrip("\n")
    assert result == 1
    assert out == "Fail"


def test_cli_set_scope_adds_layer():
    """Create a scope via @ selector and preserve body layout."""
    out = transform_with_cli("{ foo = 1; }\n", ["set", "@bar", "2"])
    assert out == "let\n  bar = 2;\nin\n{ foo = 1; }"


def test_cli_rm_scope_prunes_layer():
    """Remove a scope binding and unwrap the let when empty."""
    original = "let\n  bar = 2;\nin\n{\n  foo = 1;\n}\n"
    out = transform_with_cli(original, ["rm", "@bar"])
    assert out == "{\n  foo = 1;\n}"


def test_cli_set_outer_scope_example():
    """Follow docs example for editing an outer scope binding with @@."""
    original = dedent(
        """\
        let
          a = 1;
        in
        let
          b = 2;
        in
        { c = a + b; }
        """
    )
    expected = dedent(
        """\
        let
          a = 10;
        in
        let
          b = 2;
        in
        { c = a + b; }
        """
    ).rstrip("\n")
    out = transform_with_cli(original, ["set", "@@a", "10"])
    assert out == expected


def test_cli_set_nested_scope_binding_example():
    """Follow docs example for editing a nested binding inside a scope."""
    original = dedent(
        """\
        let
          foo = { bar = 1; baz = 3; };
        in
        { }
        """
    )
    expected = dedent(
        """\
        let
          foo = { bar = 2; baz = 3; };
        in
        { }
        """
    ).rstrip("\n")
    out = transform_with_cli(original, ["set", "@foo.bar", "2"])
    assert out == expected


def test_cli_set_follows_identifier_body_in_with(capsys):
    """CLI set should follow identifier references when targeting the body."""
    original = dedent(
        """\
        with { body = { foo = 1; }; };
        body
        """
    )
    expected = "with { body = { foo = 2; }; };\nbody"
    out = transform_with_cli(original, command=["set", "@foo", "2"])
    assert out == expected


def test_cli_set_follows_with_scope_identifier():
    """CLI set should respect with scopes instead of overwriting indirections."""
    original = dedent(
        """\
        with {
          pkgVersion = "1.0";
          body = { version = pkgVersion; };
        };
        body
        """
    )
    expected = dedent(
        """\
        with {
          pkgVersion = "2.0";
          body = { version = pkgVersion; };
        };
        body
        """
    ).rstrip("\n")
    out = transform_with_cli(original, ["set", "version", '"2.0"'])
    assert out == expected


def test_cli_set_follows_identifier_binding():
    """CLI set should update the referenced binding instead of overriding identifiers."""
    original = '{ version = package_version; package_version = "1.0.0"; }'
    expected = '{ version = package_version; package_version = "2.0.0"; }'
    out = transform_with_cli(original, ["set", "version", '"2.0.0"'])
    assert out == expected


def test_cli_set_follows_inherit_reference():
    """CLI set should follow inherit+identifier chains to update the source binding."""
    original = dedent(
        """\
        let
          package_version = "2025.9.4";
        in
        buildPythonPackage rec {
          pname = "unsloth";
          version = package_version;
          pyproject = true;

          # Tags on the GitHub repo don't match
          src = fetchPypi {
            pname = "unsloth";
            inherit version;
            hash = "sha256-aT/RS48hBMZT1ab1Rx1lpSMi6yyEzJCASzDAP0d6ixA=";
          };
        }
        """
    )
    expected = dedent(
        """\
        let
          package_version = "2026.1.2";
        in
        buildPythonPackage rec {
          pname = "unsloth";
          version = package_version;
          pyproject = true;

          # Tags on the GitHub repo don't match
          src = fetchPypi {
            pname = "unsloth";
            inherit version;
            hash = "sha256-aT/RS48hBMZT1ab1Rx1lpSMi6yyEzJCASzDAP0d6ixA=";
          };
        }
        """
    ).rstrip("\n")
    out = transform_with_cli(original, ["set", "src.version", '"2026.1.2"'])
    assert out == expected


def test_cli_set_handles_asserted_parenthesized_select_call():
    """CLI set should edit attrsets inside asserted parenthesized select calls."""
    original = dedent(
        """\
        { lib, stdenv }:
        assert stdenv.isLinux;
        (stdenv.mkDerivation {
          pname = "x";
          meta = { broken = false; };
        })
        """
    )
    expected = original.replace("broken = false;", "broken = true;").rstrip("\n")
    out = transform_with_cli(original, ["set", "meta.broken", "true"])
    assert out == expected


def test_cli_set_meta_broken_in_buildgo_lambda_argument():
    """CLI set should update nested meta attrs in constructor lambda arguments."""
    original = dedent(
        """\
        {
          lib,
          buildGo124Module,
        }:

        buildGo124Module (finalAttrs: {
          meta = {
            maintainers = with lib.maintainers; [ maintainer ];
          };
        })
        """
    )
    expected = dedent(
        """\
        {
          lib,
          buildGo124Module,
        }:

        buildGo124Module (finalAttrs: {
          meta = {
            maintainers = with lib.maintainers; [ maintainer ];
            broken = true;
          };
        })
        """
    ).rstrip("\n")
    out = transform_with_cli(original, ["set", "meta.broken", "true"])
    assert out == expected


def test_cli_scope_set_rm_restores_trivia():
    """Creating then removing a scope should keep leading/trailing comments."""
    original = "# heading\n\n{ foo = 1; }\n\n# footer\n"
    with_bar = transform_with_cli(original, ["set", "@bar", "2"])
    roundtrip = transform_with_cli(with_bar, ["rm", "@bar"])
    assert roundtrip == original.rstrip("\n")
