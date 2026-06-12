"""Tests for task management commands.

Consolidates tests from the original test_task_commands.py, plus task tests
formerly in test_task_coverage.py and test_final_coverage.py.
"""

from __future__ import annotations

import json
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core import Config
from clickup.core.exceptions import ClickUpError
from clickup.core.models import Comment, PriorityInfo, StatusInfo, Task, Team, User
from clickup.core.models import List as ClickUpList

from .conftest import make_mock_ctx

runner = CliRunner()


@pytest.fixture
def sample_tasks():
    """Sample tasks for testing."""
    tasks = []
    # date_updated is strictly increasing so sort tests can assert ordering.
    base_ts = 1_700_000_000_000
    for i, (name, status, priority) in enumerate(
        [
            ("Test Task 1", "to do", "high"),
            ("Test Task 2", "in progress", "medium"),
            ("Test Task 3", "complete", "low"),
        ],
        1,
    ):
        task = Mock()
        task.id = f"task{i}"
        task.name = name
        task.status = StatusInfo(status=status)
        task.priority = PriorityInfo(priority=priority)
        task.assignees = []
        task.due_date = None
        task.description = f"Description for {name}"
        task.date_created = str(base_ts + i * 1000)
        task.date_updated = str(base_ts + i * 1000)
        # Fix the closure issue with lambda
        task.__str__ = lambda n=name: n
        task.__repr__ = lambda n=name: f"Task({n})"
        # Add model_dump method for export functionality
        task.model_dump = lambda i=i, name=name, status=status, priority=priority: {
            "id": f"task{i}",
            "name": name,
            "status": {"status": status},
            "priority": {"priority": priority},
            "assignees": [],
            "due_date": None,
            "description": f"Description for {name}",
        }
        tasks.append(task)
    return tasks


@pytest.fixture
def sample_task_detail():
    """Sample detailed task for testing."""
    task = Mock()
    task.id = "task123"
    task.name = "Detailed Task"
    task.description = "A detailed task description"
    task.status = StatusInfo(status="in progress")
    task.priority = PriorityInfo(priority="high")
    task.assignees = [Mock(username="john.doe")]
    task.due_date = "2024-12-31"
    task.date_created = "2024-01-01"
    task.date_updated = "2024-01-02"
    task.url = "https://app.clickup.com/t/task123"
    task.tags = ["bug", "urgent"]
    task.custom_fields = {}
    # Fix the closure issue with lambda
    task.__str__ = lambda: "Detailed Task"
    task.__repr__ = lambda: "Task(Detailed Task)"
    return task


@patch("clickup.cli.commands.task.get_client")
def test_task_list(mock_get_client, sample_tasks):
    """Test listing tasks in a list."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "list123"])

    assert result.exit_code == 0
    assert "Test Task 1" in result.stdout
    assert "Test Task 2" in result.stdout
    assert "Test Task 3" in result.stdout
    assert "to do" in result.stdout
    assert "in progress" in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_task_get(mock_get_client, sample_task_detail):
    """Test getting task details."""
    mock_client = AsyncMock()
    mock_client.get_task.return_value = sample_task_detail

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["--format", "table", "task", "get", "task123"])

    assert result.exit_code == 0
    assert "Detailed Task" in result.stdout
    assert "A detailed task description" in result.stdout
    assert "high" in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_task_create(mock_get_client):
    """Test creating a new task."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "new_task"
    task_mock.name = "New Task"
    mock_client.create_task.return_value = task_mock

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app, ["task", "create", "New Task", "--list-id", "list123", "--description", "A new task description"]
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "new_task"
    assert data["name"] == "New Task"


@patch("clickup.cli.commands.task.get_client")
def test_task_update(mock_get_client):
    """Test updating an existing task."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "task123"
    task_mock.name = "Updated Task"
    mock_client.update_task.return_value = task_mock

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app, ["task", "update", "task123", "--name", "Updated Task", "--description", "Updated description"]
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "task123"
    assert data["name"] == "Updated Task"


@patch("clickup.cli.commands.task.get_client")
def test_task_update_task_ids_batch(mock_get_client):
    """`task update --task-ids` updates an explicit computed ID set."""
    mock_client = AsyncMock()
    mock_client.update_task.side_effect = [
        Mock(id="task1", name="One"),
        Mock(id="task2", name="Two"),
    ]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "update", "--task-ids", "task1,task2", "--priority", "2"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert [task["id"] for task in data["data"]] == ["task1", "task2"]
    assert mock_client.update_task.await_args_list[0].args == ("task1",)
    assert mock_client.update_task.await_args_list[0].kwargs == {"priority": 2}
    assert mock_client.update_task.await_args_list[1].args == ("task2",)
    assert mock_client.update_task.await_args_list[1].kwargs == {"priority": 2}


@patch("clickup.cli.commands.task.get_client")
def test_task_delete(mock_get_client):
    """Test deleting a task."""
    mock_client = AsyncMock()
    mock_client.delete_task.return_value = True

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "task123", "--force"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == {"id": "task123", "deleted": True}


def test_task_delete_without_flag_refuses():
    """Delete must require --force/--yes — never prompts."""
    result = runner.invoke(app, ["task", "delete", "task999"])
    assert result.exit_code == 2
    assert "Refusing to delete" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_delete_with_yes(mock_get_client):
    """--yes is an alias for --force on task delete."""
    mock_client = AsyncMock()
    mock_client.delete_task.return_value = True

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "task123", "--yes"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == {"id": "task123", "deleted": True}


def _status_mock_client():
    """Build a mocked client that records update_task calls for status tests."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "task123"
    task_mock.name = "Test Task"
    mock_client.update_task.return_value = task_mock

    def create():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    return mock_client, create


@patch("clickup.cli.commands.task.get_client")
def test_task_status_change_flag_form(mock_get_client):
    """Back-compat: --task-id / --status flag form still works."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "status", "--task-id", "task123", "--status", "in progress"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "task123"
    assert data["name"] == "Test Task"
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


@patch("clickup.cli.commands.task.get_client")
def test_task_status_change_positional(mock_get_client):
    """`task status TASK_ID STATUS` positional form works."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "status", "task123", "in progress"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "task123"
    assert data["name"] == "Test Task"
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


@patch("clickup.cli.commands.task.get_client")
def test_task_status_task_ids_batch(mock_get_client):
    """`task status --task-ids` updates a specific set of tasks in one invocation."""
    mock_client = AsyncMock()
    task1 = Mock(id="task1", name="One")
    task2 = Mock(id="task2", name="Two")
    mock_client.update_task.side_effect = [task1, task2]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "status", "--task-ids", "task1,task2", "--status", "complete"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert [task["id"] for task in data["data"]] == ["task1", "task2"]
    assert mock_client.update_task.await_args_list[0].args == ("task1",)
    assert mock_client.update_task.await_args_list[0].kwargs == {"status": "complete"}
    assert mock_client.update_task.await_args_list[1].args == ("task2",)
    assert mock_client.update_task.await_args_list[1].kwargs == {"status": "complete"}


def test_task_status_missing_args_exits_2():
    """No task_id / no status is a usage error (exit 2) with a Usage hint on stderr."""
    result = runner.invoke(app, ["task", "status"])
    assert result.exit_code == 2
    assert "Task ID is required" in result.stderr
    assert "Usage: clickup task status TASK_ID STATUS" in result.stderr


def test_task_status_conflict_positional_and_flag_exits_2():
    """Mixing positional + flag for the same param is a usage error (exit 2)."""
    result = runner.invoke(
        app,
        ["task", "status", "task123", "in progress", "--task-id", "task456"],
    )
    assert result.exit_code == 2
    assert "either as a positional argument OR via --task-id" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_done_short_verb(mock_get_client):
    """`task done <id>` sets status to 'complete'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "done", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="complete")


@patch("clickup.cli.commands.task.get_client")
def test_task_done_override_status(mock_get_client):
    """`task done <id> --status closed` honors the override."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "done", "task123", "--status", "closed"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="closed")


@patch("clickup.cli.commands.task.get_client")
def test_task_close_short_verb(mock_get_client):
    """`task close <id>` is an alias for `task done`."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "close", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="complete")


@patch("clickup.cli.commands.task.get_client")
def test_task_start_short_verb(mock_get_client):
    """`task start <id>` sets status to 'in progress'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "start", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


@patch("clickup.cli.commands.task.get_client")
def test_task_park_short_verb(mock_get_client):
    """`task park <id>` sets status to 'on-deck'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "park", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="on-deck")


@patch("clickup.cli.commands.task.get_client")
def test_task_list_with_filters(mock_get_client, sample_tasks):
    """Test listing tasks with filters."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        [
            "--format",
            "table",
            "task",
            "list",
            "--list-id",
            "list123",
            "--status",
            "in progress",
            "--assignee",
            "john.doe",
        ],
    )

    assert result.exit_code == 0
    assert "Test Task" in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_task_list_multi_status_filter(mock_get_client, sample_tasks):
    """Comma-separated --status becomes the API statuses array."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--list-id", "list123", "--status", "in progress,on-deck"])

    assert result.exit_code == 0
    mock_client.get_tasks.assert_awaited_once_with("list123", statuses=["in progress", "on-deck"])


@patch("clickup.cli.commands.task.get_client")
def test_task_list_date_filters_use_clickup_params(mock_get_client, sample_tasks):
    """Date flags map to ClickUp's epoch-ms query parameters."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        [
            "task",
            "list",
            "--list-id",
            "list123",
            "--created-after",
            "2026-05-01",
            "--updated-before",
            "2026-05-10",
        ],
    )

    assert result.exit_code == 0
    mock_client.get_tasks.assert_awaited_once_with(
        "list123",
        date_created_gt=1777593600000,
        date_updated_lt=1778371200000,
    )


@patch("clickup.cli.commands.task.get_client")
def test_task_list_multiple_lists_fans_out_and_merges(mock_get_client, sample_tasks):
    """Comma-separated --list-id queries each list and returns one merged collection."""
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = [[sample_tasks[0]], [sample_tasks[1]]]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--list-id", "listA,listB"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert data["data"][0]["source_list_id"] == "listA"
    assert data["data"][1]["source_list_id"] == "listB"
    assert [call.args[0] for call in mock_client.get_tasks.await_args_list] == ["listA", "listB"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_all_lists_uses_configured_default_lists(mock_get_client, sample_tasks, monkeypatch, tmp_path):
    """--all-lists queries each configured default_lists value."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    Config().set("default_lists", {"work": "listA", "home": "listB"})

    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = [[sample_tasks[0]], [sample_tasks[1]]]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--all-lists"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert data["data"][0]["source_list_id"] == "listA"
    assert data["data"][1]["source_list_id"] == "listB"
    assert [call.args[0] for call in mock_client.get_tasks.await_args_list] == ["listA", "listB"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_all_lists_sorts_globally_not_per_list(mock_get_client, sample_tasks, monkeypatch, tmp_path):
    """--all-lists + --sort merges and sorts globally (issue #29 P0 #3).

    Pre-fix the sort was applied per-list and the buckets were concatenated.
    Now the merged list is sorted as one set, so the highest-priority task in
    *any* list wins the top slot.
    """
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    Config().set("default_lists", {"work": "listA", "home": "listB"})

    sample_tasks[0].priority = PriorityInfo(priority="4")  # task1 in listA
    sample_tasks[1].priority = PriorityInfo(priority="1")  # task2 in listB
    sample_tasks[2].priority = PriorityInfo(priority="2")  # task3 in listB

    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = [[sample_tasks[0]], [sample_tasks[1], sample_tasks[2]]]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--all-lists", "--sort", "priority"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    # Global sort: priority 1, 2, 4. Pre-fix this came back in [listA-then-listB]
    # concat order, i.e. task1, task2, task3 (priority 4, 1, 2).
    assert [task["id"] for task in data["data"]] == ["task2", "task3", "task1"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_unknown_field_is_usage_error(mock_get_client, sample_tasks):
    """--sort fartfield is rejected (issue #29 P0 #4 / Agent 15)."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["task", "list", "--list-id", "L", "--sort", "fartfield"])
    assert result.exit_code == 2
    assert "invalid --sort field" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_statuses_json(mock_get_client):
    """`task statuses` emits allowed list statuses in JSON mode."""
    mock_client = AsyncMock()
    mock_client.get_list.return_value = ClickUpList(
        id="list123",
        name="Sprint",
        statuses=[
            {"status": "to do", "type": "open", "color": "#aaa", "orderindex": 0},
            {"status": "complete", "type": "closed", "color": "#0f0", "orderindex": 1},
        ],
    )

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "statuses", "--list-id", "list123"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["list_id"] == "list123"
    assert data["list_name"] == "Sprint"
    assert data["count"] == 2
    assert data["data"][0]["status"] == "to do"


def test_task_statuses_missing_list_errors():
    result = runner.invoke(app, ["task", "statuses"])
    assert result.exit_code == 2
    assert "No list ID" in result.stderr


def test_task_list_missing_list_id():
    """Test task list without list ID — error and hint both go to stderr now."""
    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code != 0
    # render_error + hint both write to stderr; CliRunner merges into .output by default.
    assert "list" in result.output.lower() or "workspace" in result.output.lower()


# --- task list: --sort direction-aware syntax ---


def _sort_list_mock(mock_get_client, sample_tasks):
    """Return the mock client wired to record get_tasks kwargs for sort tests."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def factory():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = factory
    return mock_client


def _task_ids_in_order(stdout: str, all_ids: list[str]) -> list[str]:
    """Return task IDs in the order they appear in the rendered table."""
    positions = [(stdout.find(tid), tid) for tid in all_ids if tid in stdout]
    return [tid for _, tid in sorted(positions)]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plain_field_no_reverse(mock_get_client, sample_tasks):
    """`--sort updated` sorts the merged result ascending by date_updated."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task1", "task2", "task3"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plain_field_with_reverse(mock_get_client, sample_tasks):
    """`--sort updated --reverse` sorts descending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(
        app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated", "--reverse"]
    )
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_colon_desc(mock_get_client, sample_tasks):
    """`--sort updated:desc` sorts descending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:desc"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_colon_asc(mock_get_client, sample_tasks):
    """`--sort updated:asc` sorts ascending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:asc"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task1", "task2", "task3"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_minus_prefix(mock_get_client, sample_tasks):
    """`--sort -updated` sorts descending (git/jq style)."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "-updated"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plus_prefix(mock_get_client, sample_tasks):
    """`--sort +updated` sorts ascending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "+updated"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task1", "task2", "task3"]


def test_task_list_sort_explicit_direction_with_reverse_is_usage_error():
    """`--sort updated:desc --reverse` is rejected (exit 2)."""
    result = runner.invoke(app, ["task", "list", "--list-id", "L", "--sort", "updated:desc", "--reverse"])
    assert result.exit_code == 2
    assert "--reverse" in result.stderr


def test_task_list_sort_invalid_direction_is_usage_error():
    """`--sort updated:sideways` is rejected (exit 2)."""
    result = runner.invoke(app, ["task", "list", "--list-id", "L", "--sort", "updated:sideways"])
    assert result.exit_code == 2
    assert "invalid sort direction" in result.stderr


def test_task_get_missing_id():
    """Test task get without task ID."""
    result = runner.invoke(app, ["task", "get"])
    assert result.exit_code != 0


def test_task_create_missing_params():
    """Test task create without required parameters."""
    result = runner.invoke(app, ["task", "create"])
    assert result.exit_code != 0


# --- input validation regressions for issue #29 P0 #4 / Agent 15 ---


@pytest.mark.parametrize("bad_priority", ["0", "-1", "5", "99"])
def test_task_create_invalid_priority_is_usage_error(bad_priority):
    """--priority outside 1..4 is rejected at the CLI boundary."""
    result = runner.invoke(app, ["task", "create", "X", "--list-id", "L", "--priority", bad_priority])
    assert result.exit_code == 2
    assert "--priority must be" in result.stderr


@pytest.mark.parametrize("bad_priority", ["0", "-1", "5", "99"])
def test_task_update_invalid_priority_is_usage_error(bad_priority):
    """--priority outside 1..4 is rejected at the CLI boundary."""
    result = runner.invoke(app, ["task", "update", "T1", "--priority", bad_priority])
    assert result.exit_code == 2
    assert "--priority must be" in result.stderr


@pytest.mark.parametrize("bad_name", ["", "   ", "\t"])
def test_task_create_empty_name_is_usage_error(bad_name):
    """Empty / whitespace-only names are rejected (issue #29 P0 #4)."""
    result = runner.invoke(app, ["task", "create", bad_name, "--list-id", "L"])
    assert result.exit_code == 2
    assert "empty" in result.stderr.lower()


def test_task_update_empty_name_is_usage_error():
    """--name '' or whitespace is rejected (use --description '' to clear instead)."""
    result = runner.invoke(app, ["task", "update", "T1", "--name", "   "])
    assert result.exit_code == 2
    assert "empty" in result.stderr.lower()


@patch("clickup.cli.commands.task.get_client")
def test_task_list_empty(mock_get_client):
    """Test listing tasks when none exist."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--list-id", "empty_list"])

    assert result.exit_code == 0
    # New behavior: always emit an empty data envelope to stdout in JSON mode.
    # The "No tasks found" warn message goes to stderr.
    data = json.loads(result.stdout)
    assert data == {"data": [], "count": 0}
    assert "No tasks found" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_get_not_found(mock_get_client):
    """Test getting non-existent task."""
    mock_client = AsyncMock()
    mock_client.get_task.side_effect = Exception("Task not found")

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "get", "nonexistent"])

    assert result.exit_code != 0


def test_task_help():
    """Test task command help."""
    result = runner.invoke(app, ["task", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "get" in result.stdout
    assert "create" in result.stdout
    assert "update" in result.stdout
    assert "delete" in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_task_create_with_all_options(mock_get_client):
    """Test creating task with all available options."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "feature_task"
    task_mock.name = "Feature Task"
    mock_client.create_task.return_value = task_mock

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "Feature Task",
            "--list-id",
            "list123",
            "--description",
            "Implement new feature",
            "--priority",
            "1",
            "--assignee",
            "dev@example.com",
            "--due-date",
            "2024-12-31",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "feature_task"
    assert data["name"] == "Feature Task"


@patch("clickup.cli.commands.task.get_client")
def test_task_search(mock_get_client, sample_tasks):
    """Test searching tasks."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        ["--format", "table", "task", "search", "--query", "test", "--workspace-id", "workspace123"],
    )

    assert result.exit_code == 0
    assert "Test Task" in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_task_export_json(mock_get_client, sample_tasks):
    """Test exporting tasks to JSON."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        result = runner.invoke(
            app, ["task", "export", "--list-id", "list123", "--output", f.name, "--output-format", "json"]
        )

        assert result.exit_code == 0
        # New behavior: structured result envelope, not a success message.
        data = json.loads(result.stdout)
        assert data["exported"] >= 0
        assert data["output_file"] == f.name
        assert data["format"] == "json"


@patch("clickup.cli.commands.task.get_client")
def test_task_error_handling(mock_get_client):
    """Test task command error handling."""
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = Exception("API Error")

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "list", "--list-id", "list123"])

    assert result.exit_code != 0


@patch("clickup.cli.commands.task.get_client")
def test_task_create_empty_description_is_sent(mock_get_client):
    """--description '' must reach the provider, not be silently dropped."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "new_task"
    task_mock.name = "New Task"
    mock_client.create_task.return_value = task_mock

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "create", "New Task", "--list-id", "list123", "--description", ""])

    assert result.exit_code == 0
    kwargs = mock_client.create_task.call_args.kwargs
    assert kwargs["description"] == ""


@patch("clickup.cli.commands.task.get_client")
def test_task_create_omitted_fields_not_sent(mock_get_client):
    """Fields not passed on the command line must not appear in the payload."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "new_task"
    task_mock.name = "New Task"
    mock_client.create_task.return_value = task_mock

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "create", "New Task", "--list-id", "list123"])

    assert result.exit_code == 0
    kwargs = mock_client.create_task.call_args.kwargs
    assert "description" not in kwargs
    assert "priority" not in kwargs
    assert "assignees" not in kwargs
    assert "due_date" not in kwargs


# --- task delete --task-ids batch tests ---


@patch("clickup.cli.commands.task.get_client")
def test_task_delete_task_ids_batch(mock_get_client):
    """`task delete --task-ids` deletes multiple tasks in one invocation."""
    mock_client = AsyncMock()
    mock_client.delete_task.return_value = True

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "--task-ids", "task1,task2,task3", "--force"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3
    assert all(item["deleted"] is True for item in data["data"])
    assert [item["id"] for item in data["data"]] == ["task1", "task2", "task3"]
    assert mock_client.delete_task.await_count == 3


@patch("clickup.cli.commands.task.get_client")
def test_task_delete_single_positional_still_works(mock_get_client):
    """Single positional task_id still works for backward compat."""
    mock_client = AsyncMock()
    mock_client.delete_task.return_value = True

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "task999", "--force"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == {"id": "task999", "deleted": True}


def test_task_delete_both_positional_and_task_ids_exits_2():
    """Passing both positional TASK_ID and --task-ids is a usage error."""
    result = runner.invoke(app, ["task", "delete", "task1", "--task-ids", "task2", "--force"])
    assert result.exit_code == 2
    assert "either as positional arguments OR via --task-ids" in result.stderr


def test_task_delete_neither_positional_nor_task_ids_exits_2():
    """Passing neither positional TASK_ID nor --task-ids is a usage error."""
    result = runner.invoke(app, ["task", "delete", "--force"])
    assert result.exit_code == 2
    assert "Task ID or --task-ids is required" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_delete_variadic_positional(mock_get_client):
    """Multiple positional IDs produce a collection envelope."""
    mock_client = AsyncMock()
    mock_client.delete_task.return_value = True

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "task1", "task2", "--force"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert all(item["deleted"] is True for item in data["data"])
    assert [item["id"] for item in data["data"]] == ["task1", "task2"]
    assert mock_client.delete_task.await_count == 2


def test_task_delete_batch_without_force_exits_2():
    """--task-ids without --force is refused (exit 2)."""
    result = runner.invoke(app, ["task", "delete", "--task-ids", "task1,task2"])
    assert result.exit_code == 2
    assert "Refusing to delete" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_delete_partial_failure_reflects_in_output(mock_get_client):
    """When some deletions fail, output shows deleted=false and exit code is 1."""
    from clickup.core import ClickUpError

    mock_client = AsyncMock()
    mock_client.delete_task.side_effect = [
        True,
        ClickUpError("Not found"),
        True,
    ]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["task", "delete", "--task-ids", "task1,task2,task3", "--force"])

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["count"] == 3
    # task1 succeeded, task2 failed, task3 succeeded
    assert data["data"][0] == {"id": "task1", "deleted": True}
    assert data["data"][1] == {"id": "task3", "deleted": True}
    assert data["data"][2] == {"id": "task2", "deleted": False}


# --- task export --output-format tests ---


@patch("clickup.cli.commands.task.get_client")
def test_task_export_output_format_csv(mock_get_client, sample_tasks):
    """`task export --output-format csv` writes CSV."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = sample_tasks

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app, ["task", "export", "--list-id", "list123", "--output", f.name, "--output-format", "csv"]
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "csv"


def test_task_export_old_format_flag_rejected():
    """`task export --format json` is no longer accepted (exit 2)."""
    result = runner.invoke(app, ["task", "export", "--list-id", "list123", "--format", "json"])
    assert result.exit_code == 2


# --- bulk export-tasks --output-format + --format back-compat ---


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_export_output_format_flag(mock_get_client):
    """`bulk export-tasks --output-format csv` works."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app, ["bulk", "export-tasks", "--list-id", "123", "--output-format", "csv", "--output", f.name]
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "csv"


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_export_format_back_compat(mock_get_client):
    """`bulk export-tasks --format csv` still works (deprecated alias)."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "123", "--format", "csv", "--output", f.name])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "csv"


# =============================================================================
# task commands — from test_task_coverage.py
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_task_create_minimal(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="New", url="https://x")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "New", "--list-id", "L1"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "New"


@patch("clickup.cli.commands.task.get_client")
def test_task_create_all_fields(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="Full")
    mock_get_client.return_value = make_mock_ctx(mock_client)

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
    call_kwargs = mock_client.create_task.call_args.kwargs
    assert call_kwargs["name"] == "Full"
    assert call_kwargs["description"] == "desc"
    assert call_kwargs["priority"] == 2
    assert call_kwargs["status"] == "on-deck"


def test_task_create_no_list_errors():
    result = runner.invoke(app, ["task", "create", "X"])
    assert result.exit_code == 2
    assert "list" in result.output.lower()


@patch("clickup.cli.commands.task.get_client")
def test_task_create_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = ClickUpError("rate limited")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "X", "--list-id", "L1"])
    assert result.exit_code == 1
    assert "rate limited" in result.stderr


# --- update from test_task_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_update_name_and_description(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="Renamed")
    mock_get_client.return_value = make_mock_ctx(mock_client)

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
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--description", ""])
    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    assert call_kwargs["description"] == ""


@patch("clickup.cli.commands.task.get_client")
def test_task_update_no_fields_warns(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1"])
    assert result.exit_code == 0
    assert "No updates specified" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_update_archived(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--archived"])
    assert result.exit_code == 0
    assert mock_client.update_task.call_args.kwargs["archived"] is True


# --- status from test_task_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_status_change(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "status", "--task-id", "t1", "--status", "done"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "X"


def test_task_status_missing_id_errors():
    result = runner.invoke(app, ["task", "status", "--status", "done"])
    assert result.exit_code == 2
    assert "Task ID" in result.stderr


def test_task_status_missing_status_errors():
    result = runner.invoke(app, ["task", "status", "--task-id", "t1"])
    assert result.exit_code == 2
    assert "Status" in result.stderr


# --- search from test_task_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_search_finds_results(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [Task(id="t1", name="Match")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Match" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_search_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "No tasks found" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_search_bare_enumerates_all(mock_get_client):
    """Omitting --query is valid: workspace-wide enumeration (empty query returns all)."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [Task(id="t1", name="All")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "All" in result.output
    mock_client.search_tasks.assert_awaited_once_with("W1", "")


@patch("clickup.cli.commands.task.get_client")
def test_task_search_no_workspace_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)
    result = runner.invoke(app, ["task", "search", "--query", "foo"])
    assert result.exit_code == 1
    assert "workspace" in result.stderr.lower()


# --- export from test_task_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_export_json_cov(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--output-format", "json"],
        )
    assert result.exit_code == 0
    from pathlib import Path

    data = json.loads(Path(f.name).read_text())
    assert data[0]["name"] == "One"


@patch("clickup.cli.commands.task.get_client")
def test_task_export_csv_cov(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--output-format", "csv"],
        )
    assert result.exit_code == 0
    from pathlib import Path

    content = Path(f.name).read_text()
    assert "id,name,status" in content
    assert "One" in content


@patch("clickup.cli.commands.task.get_client")
def test_task_export_unsupported_format_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        result = runner.invoke(
            app,
            ["task", "export", "--list-id", "L1", "--output", f.name, "--output-format", "xml"],
        )
    assert result.exit_code == 1
    assert "Unsupported" in result.stderr


def test_task_export_no_list_errors():
    result = runner.invoke(app, ["task", "export"])
    assert result.exit_code != 0


# --- mine from test_task_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_with_explicit_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [Task(id="t1", name="Mine")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Mine" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_auto_detects_single_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = [Team(id="W1", name="Solo", color="#000", members=[])]
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 0
    assert "No tasks assigned" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_no_workspaces_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 1


@patch("clickup.cli.commands.task.get_client")
def test_task_mine_multiple_workspaces_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = [
        Team(id="W1", name="A", color="#000", members=[]),
        Team(id="W2", name="B", color="#000", members=[]),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 1


# --- comments from test_task_coverage.py ---


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
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "list", "t1"])
    assert result.exit_code == 0
    assert "hi" in result.output


@patch("clickup.cli.commands.task.get_client")
def test_task_comments_list_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task_comments.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "list", "t1"])
    assert result.exit_code == 0
    assert "No comments" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_comments_add(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_comment.return_value = Mock(id="c1")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "add", "t1", "hello"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "c1"


# --- task error paths from test_final_coverage.py ---


@patch("clickup.cli.commands.task.get_client")
def test_task_get_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task.side_effect = ClickUpError("not found")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "get", "t1"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_task_list_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = ClickUpError("rate limit")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "list", "--list-id", "L1"])
    assert result.exit_code == 1


@patch("clickup.cli.commands.task.get_client")
def test_task_list_with_filters_cov(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="X")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

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


# =============================================================================
# --brief on mutation responses (item 4)
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_task_create_brief_omits_description(mock_get_client):
    """--brief on create returns the stripped projection (no description)."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(
        id="t1", name="Brief", description="long detailed text", url="https://x"
    )
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "Brief", "--list-id", "L1", "--brief"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"
    assert data["name"] == "Brief"
    assert "description" not in data


@patch("clickup.cli.commands.task.get_client")
def test_task_update_brief_omits_description(mock_get_client):
    """--brief on update returns the stripped projection (no description)."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="Updated", description="some desc", url="https://x")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--name", "Updated", "--brief"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"
    assert data["name"] == "Updated"
    assert "description" not in data


@patch("clickup.cli.commands.task.get_client")
def test_task_status_brief_omits_description(mock_get_client):
    """--brief on status returns the stripped projection (no description)."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X", description="verbose desc", url="https://x")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "status", "t1", "complete", "--brief"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"
    assert "description" not in data
