"""Integration tests for CLI commands (config, help, and misc entry points).

Consolidates tests from the original test_cli_commands.py, plus config tests
formerly in test_command_coverage.py and test_more_coverage.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import User

from .conftest import make_mock_ctx

runner = CliRunner()


def test_cli_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "ClickUp Toolkit CLI"
    assert "version" in data


def test_cli_status_no_token():
    """Test status command without API token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_overrides = {
            "HOME": tmpdir,
            "CLICKUP_API_TOKEN": "",
            "CLICKUP_API_KEY": "",
            "CLICKUP_TOKEN": "",
            "CLICKUP_ACCESS_TOKEN": "",
            "CLICKUP_CLIENT_ID": "",
            "CLICKUP_CLIENT_SECRET": "",
        }
        with patch.dict("os.environ", env_overrides, clear=False):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["api_token"] == "Not configured"


def test_config_set_token():
    """Test setting API token via CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set-token", "test_token_123"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["key"] == "api_token"
            assert data["value"] == "********"


def test_config_show():
    """Test showing configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            runner.invoke(app, ["config", "set-token", "test_token_123"])

            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "api_token" in data


def test_config_set_get():
    """Test setting and getting configuration values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "timeout", "60"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["key"] == "timeout"
            assert data["value"] == "60"

            result = runner.invoke(app, ["config", "get", "timeout"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert str(data["value"]) == "60"


def test_config_set_unknown_key_warns():
    """Unknown config keys warn but are stored (forward compat)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "some_unknown_key", "value"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["key"] == "some_unknown_key"
            assert "not a recognised config key" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_list_no_token(mock_get_client):
    """Test task list command without API token."""
    mock_get_client.side_effect = Exception("No API token configured")

    result = runner.invoke(app, ["task", "list", "--list-id", "123"])
    assert result.exit_code == 1


@patch("clickup.cli.commands.task.get_client")
async def test_task_create_success(mock_get_client):
    """Test successful task creation."""
    # Mock the async client
    mock_client = AsyncMock()
    mock_task = Mock()
    mock_task.name = "Test Task"
    mock_task.id = "task123"
    mock_task.url = "https://app.clickup.com/t/task123"

    mock_client.__aenter__.return_value = mock_client
    mock_client.create_task.return_value = mock_task
    mock_get_client.return_value = mock_client

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            # Set up config first
            runner.invoke(app, ["config", "set-token", "test_token"])
            runner.invoke(app, ["config", "set", "default_list_id", "123456"])

            result = runner.invoke(app, ["task", "create", "Test Task"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["id"] == "task123"
            assert data["name"] == "Test Task"


def test_template_list():
    """Test listing templates."""
    result = runner.invoke(app, ["template", "list"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = [r["name"] for r in data["data"]]
    assert "bug_report" in names
    assert "feature_request" in names


def test_template_show():
    """Test showing template details."""
    result = runner.invoke(app, ["template", "show", "bug_report"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "Bug Description" in data["description"]


def test_template_show_nonexistent():
    """Test showing non-existent template."""
    result = runner.invoke(app, ["template", "show", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_list(mock_get_client):
    """Test listing workspaces."""
    mock_client = AsyncMock()
    mock_team = Mock()
    mock_team.id = "team123"
    mock_team.name = "Test Team"
    mock_team.color = "#ff0000"
    mock_team.members = []

    mock_client.__aenter__.return_value = mock_client
    mock_client.get_teams.return_value = [mock_team]
    mock_get_client.return_value = mock_client

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            runner.invoke(app, ["config", "set-token", "test_token"])

            result = runner.invoke(app, ["workspace", "list"])
            assert result.exit_code == 0


def test_bulk_export_no_list():
    """Test bulk export without list ID."""
    result = runner.invoke(app, ["bulk", "export-tasks"])
    # Should show help/usage since list_id is required
    assert result.exit_code != 0


def test_bulk_import_nonexistent_file():
    """Test bulk import with non-existent file."""
    result = runner.invoke(app, ["bulk", "import-tasks", "nonexistent.csv", "--list-id", "123456"])
    assert result.exit_code in (1, 2)
    assert "File not found" in result.output


def test_cli_help():
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ClickUp CLI" in result.stdout
    assert "task" in result.stdout
    assert "config" in result.stdout
    assert "workspace" in result.stdout


def test_task_help():
    """Test task subcommand help."""
    result = runner.invoke(app, ["task", "--help"])
    assert result.exit_code == 0
    assert "Task management" in result.stdout
    assert "create" in result.stdout
    assert "list" in result.stdout
    assert "update" in result.stdout


def test_config_help():
    """Test config subcommand help."""
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "Configuration" in result.stdout
    assert "set-token" in result.stdout
    assert "show" in result.stdout


# =============================================================================
# config: from test_command_coverage.py
# =============================================================================


def test_config_set_client_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["config", "set-client-id", "client_123"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["key"] == "client_id"


def test_config_set_client_secret():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["config", "set-client-secret", "secret_456"])
            assert result.exit_code == 0


def test_config_get_unset():
    """`config get` on missing key emits null value."""
    result = runner.invoke(app, ["config", "get", "nonexistent_key_xyz"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["value"] is None


def test_config_show_json():
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0


def test_config_clean_no_unknowns():
    """Clean is a no-op when there are no unknown keys."""
    result = runner.invoke(app, ["config", "clean"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["unknown_keys"] == 0


def test_config_clean_dry_run():
    """Plant an unknown key, then dry-run shouldn't remove it or refuse."""
    from clickup.core import Config

    cfg = Config()
    cfg_path = Path(cfg._get_config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"default_team_id": "T1", "_garbage": "xx"}))

    result = runner.invoke(app, ["config", "clean", "--dry-run"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert data["would_remove"] == 1


def test_config_clean_with_force_removes():
    from clickup.core import Config

    cfg = Config()
    cfg_path = Path(cfg._get_config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"default_team_id": "T1", "_garbage": "xx"}))

    result = runner.invoke(app, ["config", "clean", "--force"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["removed"] == 1


def test_config_set_default_list():
    result = runner.invoke(app, ["config", "set-default-list", "myalias", "12345"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["alias"] == "myalias"


def test_config_set_default_list_remove():
    runner.invoke(app, ["config", "set-default-list", "myalias", "12345"])
    result = runner.invoke(app, ["config", "set-default-list", "--remove", "myalias"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["action"] == "removed"


def test_config_set_default_list_remove_missing_errors():
    result = runner.invoke(app, ["config", "set-default-list", "--remove", "nonexistent"])
    assert result.exit_code == 1


def test_config_set_default_list_no_id_errors():
    result = runner.invoke(app, ["config", "set-default-list", "myalias"])
    assert result.exit_code == 1
    assert "list_id" in result.output


# =============================================================================
# config validate / whoami — from test_more_coverage.py
# =============================================================================


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_valid_token(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (
        True,
        "Authenticated",
        User(id=1, username="evan", email="e@x.com", color="#fff", profilePicture="x"),
    )
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code == 0
            assert "evan" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_invalid_token(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "bad token", None)
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_bogus"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code == 1
            assert "bad token" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_exception(mock_client_cls):
    mock_client_cls.side_effect = Exception("network down")

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code == 1
            assert "network down" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_whoami_authenticated(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=1, username="evan", email="e@x.com", color="#fff")
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "whoami"])
            assert result.exit_code == 0
            assert "evan" in result.output


def test_config_whoami_no_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            with patch.dict("os.environ", {}, clear=False):
                from os import environ

                for k in [k for k in environ if k.startswith("CLICKUP_")]:
                    environ.pop(k, None)
                result = runner.invoke(app, ["config", "whoami"])
                assert result.exit_code == 1
                assert "credentials" in result.output.lower()


# =============================================================================
# no-credentials paths — from test_more_coverage.py
# =============================================================================


def test_workspace_list_no_credentials():
    """Without a token, workspace list refuses with a setup hint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            from os import environ

            for k in [k for k in environ if k.startswith("CLICKUP_")]:
                environ.pop(k, None)
            result = runner.invoke(app, ["workspace", "list"])
            assert result.exit_code != 0
            assert "API token" in result.output


def test_task_list_no_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            from os import environ

            for k in [k for k in environ if k.startswith("CLICKUP_")]:
                environ.pop(k, None)
            result = runner.invoke(app, ["task", "list", "--list-id", "L1"])
            assert result.exit_code != 0
