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
    assert parse(source_package).value[0].output.argument["version"].value == "1.2.3"


def test_update_version():
    code = parse(source_package)
    code.value[0].output.argument["version"] = "2.3.4"
    print(code.rebuild())
    assert code.rebuild() == source_package.replace("1.2.3", "2.3.4")
