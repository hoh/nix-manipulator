{
  lib,
  buildPythonPackage,
  fetchFromGitHub,

  # build-system
  setuptools,
  setuptools-scm,

  # dependencies
  accelerate,
  datasets,
  rich,
  transformers,
}:
let
  owner = "huggingface";
  # We love comments here
  acc = accelerate;
in
buildPythonPackage rec {
  pname = "trl";
  version = "0.19.0";
  # This is something else
  pyproject = true;

  src = fetchFromGitHub {
    # Something cool
    owner = owner;
    repo = "trl";
    tag = "v${version}";
    hash = "sha256-TlTq3tIQfNuI+CPvIy/qPFiKPhoSQd7g7FDj4F7C3CQ=";
  };

  build-system = [
    setuptools
    setuptools-scm
  ];

  /*
    We love
    multiline comments
    here
  */

  dependencies = [
    acc
    datasets
    rich
    transformers
  ];

  # Many tests require internet access.
  doCheck = false;

  pythonImportsCheck = [ "trl" ];

  meta = {
    description = "Train transformer language models with reinforcement learning";
    homepage = "https://github.com/huggingface/trl";
    changelog = "https://github.com/huggingface/trl/releases/tag/${src.tag}";
    license = lib.licenses.asl20;
    maintainers = with lib.maintainers; [ hoh ];
  };
}
