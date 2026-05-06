"""Final coverage push: setup interactive paths, bulk error paths, discover path."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.cli.output import set_format
from clickup.core.exceptions import ClickUpError
from clickup.core.models import Task

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_format():
    set_format("table")
    yield
    set_format("table")


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


# ---------- setup interactive paths -----------------------------------------


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_token_prompt(mock_client_cls, mock_prompt):
    """User enters a valid token at the prompt."""
    mock_prompt.return_value = "pk_entered"
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = []
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["setup", "run"])
            assert result.exit_code == 0
            assert mock_prompt.called


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_pick_workspace_menu(mock_client_cls, mock_prompt):
    """Two workspaces -> _pick_from_menu prompts for selection."""
    mock_prompt.return_value = "1"  # always pick first
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
    spaces = [_named(id="S1", name="X")]
    mock_client.get_teams.return_value = teams
    mock_client.get_spaces.return_value = spaces
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = []
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0
    # Picked first team via the menu
    assert "A" in result.output


@patch("clickup.cli.commands.setup.typer.confirm")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_list_use_suggested(mock_client_cls, mock_confirm):
    """confirm=Yes accepts the suggested list."""
    mock_confirm.return_value = True
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [
        _named(id="L1", name="High", task_count=10),
        _named(id="L2", name="Low", task_count=2),
    ]
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0
    assert "High" in result.output


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.typer.confirm")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_list_pick_alternative(mock_client_cls, mock_confirm, mock_prompt):
    """confirm=No, then user enters a list number."""
    mock_confirm.return_value = False
    mock_prompt.return_value = "2"  # pick the second list
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [
        _named(id="L1", name="High", task_count=10),
        _named(id="L2", name="Low", task_count=2),
    ]
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_token_validation_then_smoke_test(mock_client_cls):
    """End-to-end happy path: token works, defaults set, smoke test fetches tasks."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [_named(id="L1", name="Sprint", task_count=5)]
    mock_client.get_tasks.return_value = [
        Mock(name="task one", status=Mock(status="open")),
        Mock(name="task two", status=Mock(status="open")),
    ]
    mock_client_cls.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        ["setup", "run", "--token", "pk", "--list-id", "L1", "--non-interactive"],
    )
    assert result.exit_code == 0
    assert "smoke test" in result.output.lower()


# ---------- bulk error paths ------------------------------------------------


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_import_invalid_format(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write("<x/>")
        f.flush()
        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "L1"])
    assert result.exit_code != 0
    assert "Unsupported" in result.output or "format" in result.output.lower()


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_import_empty_file(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        f.flush()
        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "L1"])
    assert result.exit_code == 0
    assert "No tasks found" in result.output


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_export_unsupported_format(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name, "--format", "xml"],
        )
    assert result.exit_code != 0


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_update_dry_run(mock_get_client):
    mock_client = AsyncMock()
    task = Mock()
    task.id = "t1"
    task.name = "X"
    task.status = Mock()
    task.status.get = Mock(return_value="todo")
    task.priority = Mock()
    task.priority.get = Mock(return_value="medium")
    mock_client.get_tasks.return_value = [task]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1", "--status", "done", "--dry-run"])
    assert result.exit_code == 0
    assert "dry run" in result.output.lower()


# ---------- discover path -----------------------------------------------------


@patch("clickup.cli.commands.discover.get_client")
def test_discover_path_in_folder(mock_get_client):
    """Path traversal that finds the list inside a folder."""
    mock_client = AsyncMock()
    workspace = _named(id="W1", name="Acme")
    space = _named(id="S1", name="Eng")
    folder = _named(id="F1", name="Backend")
    target = _named(id="L1", name="Sprint")
    mock_client.get_list.return_value = target
    mock_client.get_teams.return_value = [workspace]
    mock_client.get_spaces.return_value = [space]
    mock_client.get_folderless_lists.return_value = []
    mock_client.get_folders.return_value = [folder]
    mock_client.get_lists.return_value = [target]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "path", "L1"])
    assert result.exit_code == 0
    assert "Acme" in result.output
    assert "Backend" in result.output


@patch("clickup.cli.commands.discover.get_client")
def test_discover_path_not_found(mock_get_client):
    """Path that doesn't find the list anywhere."""
    mock_client = AsyncMock()
    mock_client.get_list.return_value = _named(id="L999", name="Missing")
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "path", "L999"])
    assert result.exit_code == 0
    assert "Could not find" in result.output


# ---------- list create errors / api errors ---------------------------------


@patch("clickup.cli.commands.list.get_client")
def test_list_show_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_lists.side_effect = ClickUpError("nope")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--folder-id", "F1"])
    assert result.exit_code == 1


@patch("clickup.cli.commands.list.get_client")
def test_list_create_with_all_fields(mock_get_client):
    """Exercise the create_list path with all option flags set."""
    from clickup.core.models import List as ClickUpList

    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "list",
            "create",
            "New",
            "--folder-id",
            "F1",
            "--content",
            "desc",
            "--due-date",
            "2026-12-01",
            "--priority",
            "2",
            "--assignee",
            "u1",
        ],
    )
    assert result.exit_code == 0


# ---------- templates: list+show with custom dir ------------------------------


def test_templates_list_with_include_custom():
    """Test --include-custom flag with a real custom template on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            with patch("clickup.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
                # Plant a custom template file
                custom_dir = Path(tmpdir) / ".config" / "clickup-toolkit" / "templates"
                custom_dir.mkdir(parents=True, exist_ok=True)
                (custom_dir / "my_template.json").write_text(
                    json.dumps({"name": "Custom {x}", "description": "d", "variables": ["x"]})
                )

                result = runner.invoke(app, ["template", "list", "--include-custom"])
                assert result.exit_code == 0
                assert "my_template" in result.output


def test_templates_show_custom():
    """Show a custom template loaded from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            with patch("clickup.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
                custom_dir = Path(tmpdir) / ".config" / "clickup-toolkit" / "templates"
                custom_dir.mkdir(parents=True, exist_ok=True)
                (custom_dir / "test_t.json").write_text(
                    json.dumps({"name": "T {x}", "description": "Desc", "priority": 2, "variables": ["x"]})
                )

                result = runner.invoke(app, ["template", "show", "test_t"])
                assert result.exit_code == 0
                assert "Custom" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_with_template_file(mock_get_client):
    """Provide a custom template file via --template-file."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="custom_task")
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"name": "{x}", "description": "y", "priority": 3, "variables": ["x"]}, f)
        f.flush()
        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--list-id",
                "L1",
                "--template-file",
                f.name,
                "--var",
                "x=test",
                "--no-interactive",
            ],
        )
    assert result.exit_code == 0
    assert "Created task" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_template_file_missing(mock_get_client):
    """A nonexistent --template-file path errors."""
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--list-id",
            "L1",
            "--template-file",
            "/nonexistent/path.json",
            "--no-interactive",
        ],
    )
    assert result.exit_code != 0
    assert "Error loading template" in result.output


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_custom_template_by_name(mock_get_client):
    """--template <name> resolves to a custom file on disk if not built-in."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="my_task")
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
            custom_dir = Path(tmpdir) / ".config" / "clickup-toolkit" / "templates"
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "my_t.json").write_text(
                json.dumps({"name": "{n}", "description": "d", "priority": 3, "variables": ["n"]})
            )

            result = runner.invoke(
                app,
                [
                    "template",
                    "create",
                    "--list-id",
                    "L1",
                    "--template",
                    "my_t",
                    "--var",
                    "n=foo",
                    "--no-interactive",
                ],
            )
            assert result.exit_code == 0


@patch("clickup.cli.commands.templates.get_client")
def test_templates_create_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = ClickUpError("rate limit")
    mock_get_client.return_value = _ctx(mock_client)

    bug_vars = {
        "title": "x",
        "description": "x",
        "step1": "x",
        "step2": "x",
        "step3": "x",
        "expected": "x",
        "actual": "x",
        "environment": "x",
        "version": "x",
        "attachments": "x",
        "severity": "x",
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
    assert result.exit_code == 1
    assert "rate limit" in result.stderr


def test_templates_create_variables_file_missing():
    """--variables file that doesn't exist errors out."""
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
            "/nonexistent.json",
            "--no-interactive",
        ],
    )
    assert result.exit_code != 0
    assert "variables file" in result.output.lower() or "error" in result.output.lower()


# ---------- task error path: get -----------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_get_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task.side_effect = ClickUpError("not found")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "get", "t1"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_list_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = ClickUpError("rate limit")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "list", "--list-id", "L1"])
    assert result.exit_code == 1


@patch("clickup.cli.commands.task.get_client")
def test_task_list_with_filters(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="X")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "task",
            "list",
            "--list-id",
            "L1",
            "--status",
            "open",
            "--assignee",
            "u1",
            "--sort",
            "created",
            "--reverse",
        ],
    )
    assert result.exit_code == 0
    assert "X" in result.output
