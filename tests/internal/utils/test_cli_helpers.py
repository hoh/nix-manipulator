"""Exercise CLI helpers that run commands through stdin."""

import pytest

from tests.internal.cli.helpers import transform_with_cli


def test_transform_with_cli_set_updates_from_stdin():
    """Verify CLI mutations accept stdin input."""
    output = transform_with_cli("{ foo = 1; }\n", ["set", "foo", "2"])
    assert output.rstrip("\n") == "{ foo = 2; }"


def test_transform_with_cli_raises_on_failure():
    """Propagate CLI failures with stdout/stderr context."""
    with pytest.raises(RuntimeError, match="nima test failed: Fail"):
        transform_with_cli("{ foo = ; }", ["test"])


def test_transform_with_cli_strips_trailing_newlines():
    """Return stdout without trailing newlines for stable comparisons."""
    output = transform_with_cli("{ foo = 1; }\n", ["test"])
    assert output == "OK"
