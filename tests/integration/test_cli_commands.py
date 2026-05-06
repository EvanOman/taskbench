"""Integration tests for CLI commands."""

import tempfile
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app

runner = CliRunner()


def test_cli_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ClickUp Toolkit CLI" in result.stdout


def test_cli_status_no_token():
    """Test status command without API token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Clear all token environment variables and set a temp HOME
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
            assert "Not configured" in result.stdout


def test_config_set_token():
    """Test setting API token via CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set-token", "test_token_123"])
            assert result.exit_code == 0
            assert "configured successfully" in result.stdout


def test_config_show():
    """Test showing configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            # First set a token
            runner.invoke(app, ["config", "set-token", "test_token_123"])

            # Then show config
            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            assert "api_token" in result.stdout


def test_config_set_get():
    """Test setting and getting configuration values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            # Set a value
            result = runner.invoke(app, ["config", "set", "timeout", "60"])
            assert result.exit_code == 0

            # Get the value
            result = runner.invoke(app, ["config", "get", "timeout"])
            assert result.exit_code == 0
            assert "60" in result.stdout


def test_config_invalid_key():
    """Test setting invalid configuration key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            result = runner.invoke(app, ["config", "set", "invalid_key", "value"])
            assert result.exit_code == 1
            assert "Error" in result.output


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
            assert "Created task" in result.stdout


def test_template_list():
    """Test listing templates."""
    result = runner.invoke(app, ["template", "list"])
    assert result.exit_code == 0
    assert "bug_report" in result.stdout
    assert "feature_request" in result.stdout


def test_template_show():
    """Test showing template details."""
    result = runner.invoke(app, ["template", "show", "bug_report"])
    assert result.exit_code == 0
    assert "Bug Description" in result.stdout


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
