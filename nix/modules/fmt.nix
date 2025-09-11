{ inputs, ... }:
{
  imports = [ inputs.treefmt-nix.flakeModule ];

  perSystem = {
    treefmt = {
      projectRootFile = "flake.nix";
      programs = {
        jsonfmt.enable = true;
        nixfmt.enable = true;
        prettier.enable = true;
        ruff.enable = true;
        statix.enable = true;
      };
      settings = {
        on-unmatched = "fatal";
        global.excludes = [
          ".github/**"
          "*.envrc"
          ".editorconfig"
          ".prettierrc"
          "*.crt"
          "*.directory"
          "*.face"
          "*.fish"
          "*.png"
          "*.toml"
          "*.svg"
          "*.xml"
          "*/.gitignore"
          "LICENSE"
          "COPYING"
          "COPYING.LESSER"
        ];
      };
    };
  };
}
