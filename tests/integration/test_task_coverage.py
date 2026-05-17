"""Targeted tests for task command paths not yet covered.

Covers create / update / status / search / export / mine / comments,
plus a handful of error paths.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.exceptions import ClickUpError
from clickup.core.models import Comment, Task, Team, User

runner = CliRunner()


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


# ---------- create -----------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_create_minimal(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="New", url="https://x")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "New", "--list-id", "L1"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "New"


@patch("clickup.cli.commands.task.get_client")
def test_task_create_all_fields(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="Full")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "Full",
            "--list-id",
            "L1",
            "--description",
            "desc",
            "--priority",
            "2",
            "--assignee",
            "u1",
            "--due-date",
            "2026-12-01",
            "--status",
            "on-deck",
        ],
    )
    assert result.exit_code == 0
    # Verify all fields made it into the API call
    call_kwargs = mock_client.create_task.call_args.kwargs
    assert call_kwargs["name"] == "Full"
    assert call_kwargs["description"] == "desc"
    assert call_kwargs["priority"] == 2
    assert call_kwargs["status"] == "on-deck"


def test_task_create_no_list_errors():
    result = runner.invoke(app, ["task", "create", "X"])
    assert result.exit_code != 0
    assert "list" in result.output.lower()


@patch("clickup.cli.commands.task.get_client")
def test_task_create_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = ClickUpError("rate limited")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "X", "--list-id", "L1"])
    assert result.exit_code == 1
    assert "rate limited" in result.stderr


# ---------- update -----------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_update_name_and_description(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="Renamed")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--name", "Renamed", "--description", "d"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "Renamed"


@patch("clickup.cli.commands.task.get_client")
def test_task_update_clear_description_with_empty_string(mock_get_client):
    """`--description ''` should clear the field — the modify-if-passed contract."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--description", ""])
    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    assert call_kwargs["description"] == ""


@patch("clickup.cli.commands.task.get_client")
def test_task_update_no_fields_warns(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1"])
    assert result.exit_code == 0
    assert "No updates specified" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_update_archived(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--archived"])
    assert result.exit_code == 0
    assert mock_client.update_task.call_args.kwargs["archived"] is True


# ---------- status -----------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_status_change(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "status", "--task-id", "t1", "--status", "done"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "X"


def test_task_status_missing_id_errors():
    result = runner.invoke(app, ["task", "status", "--status", "done"])
    assert result.exit_code != 0
    assert "Task ID" in result.stderr


def test_task_status_missing_status_errors():
    result = runner.invoke(app, ["task", "status", "--task-id", "t1"])
    assert result.exit_code != 0
    assert "Status" in result.stderr


# ---------- search -----------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_search_finds_results(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [Task(id="t1", name="Match")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Match" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_search_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "No tasks found" in result.stderr


def test_task_search_no_query_errors():
    result = runner.invoke(app, ["task", "search", "--workspace-id", "W1"])
    assert result.exit_code != 0
    assert "query" in result.stderr.lower()


def test_task_search_no_workspace_errors():
    result = runner.invoke(app, ["task", "search", "--query", "foo"])
    assert result.exit_code != 0
    assert "workspace" in result.stderr.lower()


# ---------- export -----------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_export_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--format", "json"],
        )
    assert result.exit_code == 0
    data = json.loads(Path(f.name).read_text())
    assert data[0]["name"] == "One"


@patch("clickup.cli.commands.task.get_client")
def test_task_export_csv(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--format", "csv"],
        )
    assert result.exit_code == 0
    content = Path(f.name).read_text()
    assert "id,name,status" in content
    assert "One" in content


@patch("clickup.cli.commands.task.get_client")
def test_task_export_unsupported_format_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--format", "xml"],
        )
    assert result.exit_code != 0
    assert "Unsupported" in result.stderr


def test_task_export_no_list_errors():
    result = runner.invoke(app, ["task", "export"])
    assert result.exit_code != 0


# ---------- mine -------------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_with_explicit_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [Task(id="t1", name="Mine")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "mine", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Mine" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_auto_detects_single_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = [Team(id="W1", name="Solo", color="#000", members=[])]
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 0
    assert "No tasks assigned" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_no_workspaces_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code != 0


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_multiple_workspaces_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = [
        Team(id="W1", name="A", color="#000", members=[]),
        Team(id="W2", name="B", color="#000", members=[]),
    ]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code != 0


# ---------- comments ---------------------------------------------------------


@patch("clickup.cli.commands.task.get_client")
def test_task_comments_list(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task_comments.return_value = [
        Comment(
            id="c1",
            comment=[{"text": "hi"}],
            comment_text="hi",
            user=User(id=1, username="u", email="u@x.com"),
            date="1700000000000",
        )
    ]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "list", "t1"])
    assert result.exit_code == 0
    assert "hi" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_comments_list_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task_comments.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "list", "t1"])
    assert result.exit_code == 0
    assert "No comments" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_comments_add(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_comment.return_value = Mock(id="c1")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "add", "t1", "hello"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "c1"
