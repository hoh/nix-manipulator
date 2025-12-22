from nix_manipulator.parser import parse

source_package = """
{
  lib,
  buildPythonPackage,
}:
buildPythonPackage rec {
  pname = "hello-world";
  version = "1.2.3";

  src = fetchFromGitHub {
    owner = owner;
    repo = "trl";
    tag = "v${version}";
    hash = "sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=";
  };

  build-system = [
    setuptools
    setuptools-scm
  ];
}
""".strip("\n")


def test_get_version():
    """Verify version extraction to support update tooling accuracy."""
    assert parse(source_package).expr.output.argument["version"].value == "1.2.3"


def test_update_version():
    """Ensure version edits round-trip so updates are deterministic."""
    code = parse(source_package)
    code.expr.output.argument["version"] = "2.3.4"
    print(code.rebuild())
    assert code.rebuild() == source_package.replace("1.2.3", "2.3.4")


def test_update_version_and_hash():
    """Ensure multi-field updates keep formatting and ordering intact."""
    code = parse(source_package)
    code.expr.output.argument["version"] = "2.3.4"
    code.expr.output.argument["src"].argument["hash"] = (
        "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )
    assert (
        code.rebuild()
        == """
{
  lib,
  buildPythonPackage,
}:
buildPythonPackage rec {
  pname = "hello-world";
  version = "2.3.4";

  src = fetchFromGitHub {
    owner = owner;
    repo = "trl";
    tag = "v${version}";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };

  build-system = [
    setuptools
    setuptools-scm
  ];
}
""".strip("\n")
    )
