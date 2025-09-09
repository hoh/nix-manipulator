{
  inputs.nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems =
        f: nixpkgs.lib.genAttrs supportedSystems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);

      packages = forAllSystems (
        pkgs:
        let
          pypkgs = pkgs.python312Packages;
        in
        {
          default = pypkgs.toPythonApplication self.packages.${pkgs.system}.nix-manipulator;

          nix-manipulator = pypkgs.callPackage ./nix-manipulator.nix { };
        }
      );

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          inputsFrom = [
            (pkgs.callPackage ./default.nix { })
          ];
        };
      });
    };
}
