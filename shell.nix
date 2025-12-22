let
  nixpkgsSrc = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/refs/heads/nixos-25.11.tar.gz";
  };
  pkgs = import nixpkgsSrc {};
in
pkgs.mkShell {
  buildInputs = [
    (pkgs.callPackage ./default.nix { })
    pkgs.python313Packages.pytest
    pkgs.python313Packages.pytest-cov
  ];
  NIXPKGS_PATH = nixpkgsSrc;
}
