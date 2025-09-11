{
  perSystem =
    { config, ... }:
    {
      checks = config.packages;
    };
}
