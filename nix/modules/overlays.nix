{ withSystem, ... }:
{
  flake = {
    overlays.default =
      final: prev: withSystem prev.stdenv.hostPlatform.system ({ config, ... }: config.packages);
  };
}
