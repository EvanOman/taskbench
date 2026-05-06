"""Coverage-driven tests for templates / discover / config / main / list / workspace.

Each test exercises a previously-uncovered command path. Many are smoke tests
for table mode; JSON-mode coverage lives in test_json_format.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import (
    List as ClickUpList,
)
from clickup.core.models import (
    PriorityInfo,
    Task,
)

runner = CliRunner()


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


def _named(**kw):
    name = kw.pop("name", None)
    m = Mock(**kw)
    if name is not None:
        m.name = name
    return m


# =============================================================================
# templates
# =============================================================================


def test_templates_list_builtin():
    """Built-in templates render in table mode."""
    result = runner.invoke(app, ["template", "list"])
    assert result.exit_code == 0
    assert "bug_report" in result.output
    assert "feature_request" in result.output


def test_templates_show_builtin():
    result = runner.invoke(app, ["template", "show", "bug_report"])
    assert result.exit_code == 0
    assert "Bug Description" in result.output


def test_templates_show_missing():
    result = runner.invoke(app, ["template", "show", "nonexistent_xyz"])
    assert result.exit_code == 1
    assert "not found" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_with_variables_file(mock_get_client):
    """Use --variables file path with all bug_report vars."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="[Bug] login")
    mock_get_client.return_value = _ctx(mock_client)

    bug_vars = {
        "title": "login",
        "description": "broken",
        "step1": "x",
        "step2": "y",
        "step3": "z",
        "expected": "ok",
        "actual": "fail",
        "environment": "mac",
        "version": "1.0",
        "attachments": "none",
        "severity": "high",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bug_vars, f)
        f.flush()
        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--template",
                "bug_report",
                "--list-id",
                "L1",
                "--variables",
                f.name,
                "--no-interactive",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "Created task" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_invalid_var_format(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--template",
            "bug_report",
            "--list-id",
            "L1",
            "--var",
            "no_equals_sign",
            "--no-interactive",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid variable format" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_save_with_pattern_flags(mock_get_client):
    """Non-interactive save with --name-pattern / --description-pattern."""
    mock_client = AsyncMock()
    mock_client.get_task.return_value = Task(
        id="t1", name="Sample task", description="Sample {what}", priority=PriorityInfo(priority="2", id="2")
    )
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(
                app,
                [
                    "template",
                    "save",
                    "test-template",
                    "--from-task",
                    "t1",
                    "--name-pattern",
                    "[{kind}] {title}",
                    "--description-pattern",
                    "Doing {what}",
                ],
            )
            assert result.exit_code == 0
            assert "Saved template" in result.output


def test_templates_create_no_list_errors():
    result = runner.invoke(app, ["template", "create", "--template", "bug_report", "--no-interactive"])
    assert result.exit_code != 0


def test_templates_create_no_template_errors():
    result = runner.invoke(app, ["template", "create", "--list-id", "L1", "--no-interactive"])
    assert result.exit_code != 0


# =============================================================================
# discover ids / path
# =============================================================================


@patch("clickup.cli.commands.discover.get_client")
def test_discover_ids_lists_in_folder(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = [_named(id="L1", name="Sprint", task_count=5)]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "ids", "--folder-id", "F1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


@patch("clickup.cli.commands.discover.get_client")
def test_discover_ids_in_space(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = [_named(id="F1", name="Backend", task_count=10)]
    mock_client.get_folderless_lists.return_value = [_named(id="L1", name="Loose", task_count=2)]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "ids", "--space-id", "S1"])
    assert result.exit_code == 0
    assert "Backend" in result.output
    assert "Loose" in result.output


@patch("clickup.cli.commands.discover.get_client")
def test_discover_ids_in_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = [_named(id="S1", name="Eng", private=False, statuses=[])]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "ids", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Eng" in result.output


@patch("clickup.cli.commands.discover.get_client")
def test_discover_ids_no_args_lists_workspaces(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = [_named(id="T1", name="Acme", color="#fff", members=[])]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "ids"])
    assert result.exit_code == 0
    assert "Acme" in result.output


@patch("clickup.cli.commands.discover.get_client")
def test_discover_path_finds_list(mock_get_client):
    mock_client = AsyncMock()
    workspace = _named(id="W1", name="Acme")
    space = _named(id="S1", name="Eng")
    target_list = _named(id="L1", name="Sprint")
    mock_client.get_list.return_value = target_list
    mock_client.get_teams.return_value = [workspace]
    mock_client.get_spaces.return_value = [space]
    mock_client.get_folderless_lists.return_value = [target_list]
    mock_client.get_folders.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "path", "L1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


# =============================================================================
# config: show / whoami / validate / set-client-id / set-client-secret
# =============================================================================


def test_config_set_client_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["config", "set-client-id", "client_123"])
            assert result.exit_code == 0
            assert "Client ID configured" in result.output


def test_config_set_client_secret():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["config", "set-client-secret", "secret_456"])
            assert result.exit_code == 0


def test_config_get_unset():
    """`config get` on missing key prints not-set message."""
    result = runner.invoke(app, ["config", "get", "nonexistent_key_xyz"])
    assert result.exit_code == 0
    assert "not set" in result.output


def test_config_show():
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0


def test_config_clean_no_unknowns():
    """Clean is a no-op when there are no unknown keys."""
    result = runner.invoke(app, ["config", "clean"])
    assert result.exit_code == 0
    assert "clean" in result.output.lower()


def test_config_clean_dry_run():
    """Plant an unknown key, then dry-run shouldn't remove it or refuse."""
    from clickup.core import Config

    cfg = Config()
    cfg_path = Path(cfg._get_config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"default_team_id": "T1", "_garbage": "xx"}))

    result = runner.invoke(app, ["config", "clean", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_config_clean_with_force_removes():
    from clickup.core import Config

    cfg = Config()
    cfg_path = Path(cfg._get_config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"default_team_id": "T1", "_garbage": "xx"}))

    result = runner.invoke(app, ["config", "clean", "--force"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_config_set_default_list():
    result = runner.invoke(app, ["config", "set-default-list", "myalias", "12345"])
    assert result.exit_code == 0
    assert "myalias" in result.output


def test_config_set_default_list_remove():
    runner.invoke(app, ["config", "set-default-list", "myalias", "12345"])
    result = runner.invoke(app, ["config", "set-default-list", "--remove", "myalias"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_config_set_default_list_remove_missing_errors():
    result = runner.invoke(app, ["config", "set-default-list", "--remove", "nonexistent"])
    assert result.exit_code != 0


def test_config_set_default_list_no_id_errors():
    result = runner.invoke(app, ["config", "set-default-list", "myalias"])
    assert result.exit_code != 0
    assert "list_id" in result.output


# =============================================================================
# list commands
# =============================================================================


@patch("clickup.cli.commands.list.get_client")
def test_list_show_in_folder(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = [ClickUpList(id="L1", name="Sprint", task_count=5)]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--folder-id", "F1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


@patch("clickup.cli.commands.list.get_client")
def test_list_show_in_space(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_folderless_lists.return_value = [ClickUpList(id="L1", name="Sprint", task_count=5)]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--space-id", "S1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


def test_list_show_no_args_errors():
    result = runner.invoke(app, ["list", "show"])
    assert result.exit_code != 0


@patch("clickup.cli.commands.list.get_client")
def test_list_get(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_list.return_value = ClickUpList(
        id="L1",
        name="Sprint",
        task_count=5,
        content="some content",
        orderindex=0,
    )
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "get", "--list-id", "L1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


@patch("clickup.cli.commands.list.get_client")
def test_list_create_in_folder(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "create", "New", "--folder-id", "F1"])
    assert result.exit_code == 0


@patch("clickup.cli.commands.list.get_client")
def test_list_create_in_space(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_folderless_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "create", "New", "--space-id", "S1"])
    assert result.exit_code == 0


def test_list_create_no_parent_errors():
    result = runner.invoke(app, ["list", "create", "New"])
    assert result.exit_code != 0


# =============================================================================
# main / top-level callbacks
# =============================================================================


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ClickUp" in result.output


def test_cli_version_or_status():
    """Either --version or `status` should respond. Just smoke."""
    result = runner.invoke(app, ["status"])
    # status may exit non-zero without creds, but should produce output
    assert result.output  # non-empty


def test_cli_format_flag_global():
    """--format json is accepted at the root level."""
    result = runner.invoke(app, ["--format", "json", "template", "list"])
    assert result.exit_code == 0
    # Output may be a table for list templates if the command isn't fully migrated,
    # but the global flag should at least be accepted without error.


def test_invalid_subcommand_errors():
    result = runner.invoke(app, ["nonexistent_subcommand"])
    assert result.exit_code != 0


# =============================================================================
# bulk: extra coverage
# =============================================================================


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_export_csv(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name, "--format", "csv"],
        )
    assert result.exit_code == 0


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_import_dry_run_no_force_required(mock_get_client):
    """--dry-run should not require --force."""
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([{"name": "t1"}, {"name": "t2"}], f)
        f.flush()
        result = runner.invoke(
            app,
            ["bulk", "import-tasks", f.name, "--list-id", "L1", "--dry-run"],
        )
    assert result.exit_code == 0


# =============================================================================
# workspace: error paths
# =============================================================================


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_list_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 0
    assert "No workspaces" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_spaces_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "spaces", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "No spaces" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_folders_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "folders", "--space-id", "S1"])
    assert result.exit_code == 0
    assert "No folders" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_members_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_team_members.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "members", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "No members" in result.output
