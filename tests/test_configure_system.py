# These tests demonstrate how to use nix-manipulator to modify a NixOS system configuration.

from nix_manipulator.expressions import Identifier
from nix_manipulator.parser import parse

nixos_configuration = """
{ pkgs, ... }: {
  imports = [
    ./hardware-configuration.nix
  ];

  networking.hostName = "machine";

  environment.systemPackages = with pkgs; [
    vim
  ];

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "yes";
    };
  };

  users.users.allice = {
    isNormalUser = true;
    description = "Alice";
    extraGroups = [ "wheel" ];
    shell = pkgs.fish;
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDuwLTvcZOizLhXFb5YspQ6IYNIU7xGGizpALP0Q3Fjc hugo@okeso.eu"
    ];

    packages = with pkgs; [ ];
  };

  networking.firewall.allowedTCPPorts = [
    22
  ];

  system.stateVersion = "25.05";
}

""".strip("\n")


def test_add_system_packages():
    """This test demonstrates how to add system packages to a nixos configuration."""
    code = parse(nixos_configuration)
    system_packages = code.value[0].output["environment.systemPackages"]
    assert system_packages.body.value == [Identifier(name="vim")]

    system_packages.body.value.append(Identifier(name="helix"))

    assert system_packages.rebuild() == "with pkgs; [\n  vim\n  helix\n]"
    assert code.rebuild() == nixos_configuration.replace("vim", "vim\n    helix")


def test_add_user_packages():
    """This test demonstrates how to add packages for a specific user."""
    code = parse(nixos_configuration)
    alice_packages = code.value[0].output["users.users.allice"]["packages"]

    alice_packages.body.value.append(Identifier(name="emacs"))

    assert alice_packages.rebuild() == "with pkgs; [ emacs ]"
    assert code.rebuild() == nixos_configuration.replace(
        "with pkgs; [ ]", "with pkgs; [ emacs ]"
    )
