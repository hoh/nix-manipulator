{ inputs, ... }:
{
  imports = [ inputs.make-shell.flakeModules.default ];

  perSystem =
    { config, ... }:
    {
      make-shells.default = {
        inputsFrom = [
          config.packages.nix-manipulator
        ];
      };
    };
}
