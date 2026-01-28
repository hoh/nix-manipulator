{
  description = "Nix-manipulator (nima)";

  inputs = {
    nixpkgs.url = "github:hoh/nixpkgs?rev=e91e354e9e2dc9ca71f4e02db98af20bdd1e035e";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = import ./default.nix { inherit pkgs; };
        }
      );

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            buildInputs = [
              self.packages.${system}.default
              pkgs.python313Packages.mkdocs
              pkgs.python313Packages.mkdocs-material
              pkgs.python313Packages.pytest
              pkgs.python313Packages.pytest-cov
              pkgs.nixfmt
            ];
            NIXPKGS_PATH = nixpkgs.outPath;
          };
        }
      );
    };
}
