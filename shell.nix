let
  nixpkgsSrc = builtins.fetchTarball {
    # url = "https://github.com/hoh/nixpkgs/archive/refs/heads/fix-rfc-0166-compliance.tar.gz";
    url = "https://github.com/hoh/nixpkgs/archive/e91e354e9e2dc9ca71f4e02db98af20bdd1e035e.tar.gz";
  };
  pkgs = import nixpkgsSrc {};
in
pkgs.mkShell {
  buildInputs = [
    (pkgs.callPackage ./default.nix { })
    pkgs.python313Packages.mkdocs
    pkgs.python313Packages.mkdocs-material
    pkgs.python313Packages.pytest
    pkgs.python313Packages.pytest-cov
    pkgs.nixfmt
  ];
  NIXPKGS_PATH = nixpkgsSrc;
}
