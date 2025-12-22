import pytest

from tests import nixfmt_helpers


def test_validate_nixfmt_rfc166_accepts_rfc_formatting():
    """Ensure RFC formatting passes validation to avoid false failures."""
    code = "{ foo = 1; }"
    assert nixfmt_helpers.validate_nixfmt_rfc(code) == code


def test_validate_nixfmt_rfc166_rejects_non_rfc_formatting():
    """Ensure non-RFC formatting is rejected to enforce style rules."""
    with pytest.raises(AssertionError):
        nixfmt_helpers.validate_nixfmt_rfc("{foo=1;}")


def test_validate_nixfmt_rfc166_rejects_invalid_nix():
    """Ensure invalid Nix surfaces as a validation failure."""
    with pytest.raises(AssertionError, match="nixfmt failed to validate code"):
        nixfmt_helpers.validate_nixfmt_rfc("{")


def test_validate_nixfmt_rfc166_errors_when_nixfmt_missing(monkeypatch):
    """Ensure missing nixfmt produces a clear runtime error."""
    monkeypatch.setattr(nixfmt_helpers.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="nixfmt binary not found in PATH"):
        nixfmt_helpers.validate_nixfmt_rfc("{ foo = 1; }")
