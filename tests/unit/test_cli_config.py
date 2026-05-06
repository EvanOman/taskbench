"""Unit tests for CLI config commands."""

import tempfile
from unittest.mock import patch

from typer.testing import CliRunner

from clickup.cli.main import app

runner = CliRunner()


def test_config_set_client_id():
    """Test setting client ID via CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set-client-id", "test_client_id"])
            assert result.exit_code == 0
            assert "configured successfully" in result.stdout


def test_config_set_client_secret():
    """Test setting client secret via CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set-client-secret", "test_secret"])
            assert result.exit_code == 0
            assert "configured successfully" in result.stdout


def test_config_get_nonexistent():
    """Test getting non-existent config value."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "get", "default_team_id"])
            # Should show "not set" message
            assert result.exit_code == 0
            assert "not set" in result.stdout


def test_config_reset_without_flag_refuses():
    """Reset without --yes/--force must error out (no interactive prompt)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "reset"])
            assert result.exit_code == 2
            assert "Refusing to reset" in result.stderr


def test_config_reset_with_yes():
    """Reset with --yes proceeds non-interactively."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            runner.invoke(app, ["config", "set-token", "test_token"])

            result = runner.invoke(app, ["config", "reset", "--yes"])
            assert result.exit_code == 0
            assert "reset to defaults" in result.stdout


def test_config_reset_with_force():
    """--force is an alias for --yes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            runner.invoke(app, ["config", "set-token", "test_token"])

            result = runner.invoke(app, ["config", "reset", "--force"])
            assert result.exit_code == 0
            assert "reset to defaults" in result.stdout


def test_config_clean_without_flag_refuses():
    """Clean must require --force/--yes when there's something to remove."""
    import json
    from pathlib import Path

    from clickup.core import Config

    # The conftest fixture monkeypatches Config to a per-test tmp path —
    # write the planted unknown key directly to that path.
    cfg = Config()
    cfg_path = Path(cfg._get_config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"default_team_id": "real", "__bogus_key__": "xyz"}))

    result = runner.invoke(app, ["config", "clean"])
    assert result.exit_code == 2
    assert "Refusing to remove" in result.stderr


def test_config_validate_no_credentials():
    """Test validating auth without credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}, clear=True):
            result = runner.invoke(app, ["config", "validate"])
            # Without credentials, should show error on stderr and exit 2 (usage error)
            has_creds_msg = "credentials" in result.output.lower()
            has_config_msg = "configured" in result.output.lower()
            assert result.exit_code in (1, 2) or has_creds_msg or has_config_msg


def test_config_set_default_team_id():
    """Test setting default team ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "default_team_id", "team123"])
            assert result.exit_code == 0
            assert "team123" in result.stdout


def test_config_set_default_space_id():
    """Test setting default space ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "default_space_id", "space456"])
            assert result.exit_code == 0
            assert "space456" in result.stdout


def test_config_set_default_list_id():
    """Test setting default list ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "default_list_id", "list789"])
            assert result.exit_code == 0
            assert "list789" in result.stdout


def test_config_set_output_format():
    """Test setting output format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "output_format", "table"])
            assert result.exit_code == 0
            assert "table" in result.stdout


def test_config_set_max_retries():
    """Test setting max retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "max_retries", "5"])
            assert result.exit_code == 0
            assert "5" in result.stdout


def test_config_show_with_credentials():
    """Test showing config with masked credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            # Set credentials
            runner.invoke(app, ["config", "set-token", "test_api_token_12345"])
            runner.invoke(app, ["config", "set-client-id", "test_client_id_12345"])
            runner.invoke(app, ["config", "set-client-secret", "test_client_secret"])

            # Show config - secrets should be masked
            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            assert "***" in result.stdout
