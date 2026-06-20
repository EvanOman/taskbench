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

from taskbench.cli.main import app
from taskbench.core import Config
from taskbench.core.exceptions import ClickUpError
from taskbench.core.models import Comment, PriorityInfo, StatusInfo, Task, Team, User
from taskbench.core.models import List as ClickUpList

from .conftest import _strip_ansi, make_mock_ctx

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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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
    assert "Usage: taskbench task status TASK_ID STATUS" in result.stderr


def test_task_status_conflict_positional_and_flag_exits_2():
    """Mixing positional + flag for the same param is a usage error (exit 2)."""
    result = runner.invoke(
        app,
        ["task", "status", "task123", "in progress", "--task-id", "task456"],
    )
    assert result.exit_code == 2
    assert "either as a positional argument OR via --task-id" in result.stderr


@patch("taskbench.cli.commands.task.get_client")
def test_task_done_short_verb(mock_get_client):
    """`task done <id>` sets status to 'complete'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "done", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="complete")


@patch("taskbench.cli.commands.task.get_client")
def test_task_done_override_status(mock_get_client):
    """`task done <id> --status closed` honors the override."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "done", "task123", "--status", "closed"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="closed")


@patch("taskbench.cli.commands.task.get_client")
def test_task_close_short_verb(mock_get_client):
    """`task close <id>` is an alias for `task done`."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "close", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="complete")


@patch("taskbench.cli.commands.task.get_client")
def test_task_start_short_verb(mock_get_client):
    """`task start <id>` sets status to 'in progress'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "start", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


@patch("taskbench.cli.commands.task.get_client")
def test_task_park_short_verb(mock_get_client):
    """`task park <id>` sets status to 'on-deck'."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "park", "task123"])

    assert result.exit_code == 0
    mock_client.update_task.assert_awaited_once_with("task123", status="on-deck")


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_unknown_field_is_usage_error(mock_get_client, sample_tasks):
    """--sort fartfield is rejected (issue #29 P0 #4 / Agent 15)."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["task", "list", "--list-id", "L", "--sort", "fartfield"])
    assert result.exit_code == 2
    assert "invalid --sort field" in result.stderr


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_plain_field_no_reverse(mock_get_client, sample_tasks):
    """`--sort updated` sorts the merged result ascending by date_updated."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task1", "task2", "task3"]


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_plain_field_with_reverse(mock_get_client, sample_tasks):
    """`--sort updated --reverse` sorts descending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(
        app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated", "--reverse"]
    )
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_colon_desc(mock_get_client, sample_tasks):
    """`--sort updated:desc` sorts descending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:desc"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_colon_asc(mock_get_client, sample_tasks):
    """`--sort updated:asc` sorts ascending."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:asc"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task1", "task2", "task3"]


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_sort_minus_prefix(mock_get_client, sample_tasks):
    """`--sort -updated` sorts descending (git/jq style)."""
    _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "-updated"])
    assert result.exit_code == 0
    assert _task_ids_in_order(result.stdout, ["task1", "task2", "task3"]) == ["task3", "task2", "task1"]


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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
    # Empty results emit only the data envelope in JSON mode; the
    # "No tasks found" notice is info-level and suppressed (the count
    # already carries the signal).
    data = json.loads(result.stdout)
    assert data == {"data": [], "count": 0}
    assert "No tasks found" not in result.stdout


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_delete_partial_failure_reflects_in_output(mock_get_client):
    """When some deletions fail, output shows deleted=false and exit code is 1."""
    from taskbench.core import ClickUpError

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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.bulk.get_client")
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


@patch("taskbench.cli.commands.bulk.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_create_minimal(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="New", url="https://x")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "New", "--list-id", "L1"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "New"


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_create_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = ClickUpError("rate limited")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "X", "--list-id", "L1"])
    assert result.exit_code == 1
    assert "rate limited" in result.stderr


# --- update from test_task_coverage.py ---


@patch("taskbench.cli.commands.task.get_client")
def test_task_update_name_and_description(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="Renamed")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--name", "Renamed", "--description", "d"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "t1"
    assert data["name"] == "Renamed"


@patch("taskbench.cli.commands.task.get_client")
def test_task_update_clear_description_with_empty_string(mock_get_client):
    """`--description ''` should clear the field — the modify-if-passed contract."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--description", ""])
    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    assert call_kwargs["description"] == ""


@patch("taskbench.cli.commands.task.get_client")
def test_task_update_no_fields_warns(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1"])
    assert result.exit_code == 0
    assert "No updates specified" in result.stderr


@patch("taskbench.cli.commands.task.get_client")
def test_task_update_archived(mock_get_client):
    mock_client = AsyncMock()
    mock_client.update_task.return_value = Task(id="t1", name="X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "update", "t1", "--archived"])
    assert result.exit_code == 0
    assert mock_client.update_task.call_args.kwargs["archived"] is True


# --- status from test_task_coverage.py ---


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_search_finds_results(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [Task(id="t1", name="Match")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Match" in result.output


@patch("taskbench.cli.commands.task.get_client")
def test_task_search_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--query", "foo", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "No tasks found" not in result.stdout  # info-level notice suppressed in JSON mode


@patch("taskbench.cli.commands.task.get_client")
def test_task_search_bare_enumerates_all(mock_get_client):
    """Omitting --query is valid: workspace-wide enumeration (empty query returns all)."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [Task(id="t1", name="All")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "search", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "All" in result.output
    mock_client.search_tasks.assert_awaited_once_with("W1", "")


@patch("taskbench.cli.commands.task.get_client")
def test_task_search_no_workspace_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)
    result = runner.invoke(app, ["task", "search", "--query", "foo"])
    assert result.exit_code == 1
    assert "workspace" in result.stderr.lower()


# --- export from test_task_coverage.py ---


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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
    # Canonical CSV columns (shared with bulk export-tasks): includes
    # date_created, date_updated, url that the old task export was missing.
    assert "id,name,description,status,priority,assignees,due_date,date_created,date_updated,url" in content
    assert "One" in content


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_mine_with_explicit_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [Task(id="t1", name="Mine")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine", "--workspace-id", "W1"])
    assert result.exit_code == 0
    assert "Mine" in result.output


@patch("taskbench.cli.commands.task.get_client")
def test_task_mine_auto_detects_single_workspace(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = [Team(id="W1", name="Solo", color="#000", members=[])]
    mock_client.search_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 0
    assert "No tasks assigned" not in result.stdout  # info-level notice suppressed in JSON mode


@patch("taskbench.cli.commands.task.get_client")
def test_task_mine_no_workspaces_errors(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.get_teams.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "mine"])
    assert result.exit_code == 1


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
def test_task_comments_list_empty(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task_comments.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "list", "t1"])
    assert result.exit_code == 0
    assert "No comments" not in result.stdout  # info-level notice suppressed in JSON mode


@patch("taskbench.cli.commands.task.get_client")
def test_task_comments_add(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_comment.return_value = Mock(id="c1")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "comments", "add", "t1", "hello"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "c1"


# --- task error paths from test_final_coverage.py ---


@patch("taskbench.cli.commands.task.get_client")
def test_task_get_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_task.side_effect = ClickUpError("not found")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "get", "t1"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = ClickUpError("rate limit")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "list", "--list-id", "L1"])
    assert result.exit_code == 1


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


@patch("taskbench.cli.commands.task.get_client")
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


# =============================================================================
# Batch task create (from backlog-49 item 1)
# =============================================================================


def _make_task_b49(id: str, name: str, **overrides) -> Task:
    """Build a real Task model for tests that need model_dump."""
    kwargs = {"id": id, "name": name}
    kwargs.update(overrides)
    return Task(**kwargs)


@patch("taskbench.cli.commands.task.get_client")
def test_batch_create_three_tasks_collection_envelope(mock_get_client):
    """3 names -> 3 tasks in order, collection envelope, flags applied to all."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task_b49("t1", "Alpha", url="https://x/t1"),
        _make_task_b49("t2", "Bravo", url="https://x/t2"),
        _make_task_b49("t3", "Charlie", url="https://x/t3"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "Alpha",
            "Bravo",
            "Charlie",
            "--list-id",
            "L1",
            "--description",
            "shared desc",
            "--priority",
            "2",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3
    assert [t["name"] for t in data["data"]] == ["Alpha", "Bravo", "Charlie"]

    # Verify flags applied to every call
    for call in mock_client.create_task.await_args_list:
        assert call.kwargs["description"] == "shared desc"
        assert call.kwargs["priority"] == 2


@patch("taskbench.cli.commands.task.get_client")
def test_single_create_unchanged_shape(mock_get_client):
    """Single name produces a singleton task object, NOT a collection envelope."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task_b49("t1", "Solo", url="https://x/t1")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "Solo", "--list-id", "L1"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"
    assert data["name"] == "Solo"
    # No "data" / "count" keys — singleton shape
    assert "data" not in data
    assert "count" not in data


@patch("taskbench.cli.commands.task.get_client")
def test_batch_create_partial_failure_exit_1(mock_get_client):
    """When some creates fail: successes rendered, failures warned, exit 1."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task_b49("t1", "Good"),
        ClickUpError("rate limited"),
        _make_task_b49("t3", "Also Good"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "Good", "Bad", "Also Good", "--list-id", "L1"],
    )

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    # Only the 2 successes appear in the envelope
    assert data["count"] == 2
    assert [t["name"] for t in data["data"]] == ["Good", "Also Good"]
    # Error on stderr
    assert "Failed to create task 'Bad'" in result.stderr


@patch("taskbench.cli.commands.task.get_client")
def test_batch_create_brief(mock_get_client):
    """--brief works for batch creates."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task_b49("t1", "A", description="long text", url="https://x"),
        _make_task_b49("t2", "B", description="long text 2", url="https://x"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "A", "B", "--list-id", "L1", "--brief"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    for t in data["data"]:
        assert "description" not in t


def test_batch_create_validates_each_name():
    """Each name is validated — empty names rejected."""
    result = runner.invoke(app, ["task", "create", "Good", "   ", "--list-id", "L1"])
    assert result.exit_code == 2
    assert "empty" in result.stderr.lower()


# =============================================================================
# Zero-result hints (from backlog-49 item 3)
# =============================================================================


@patch("taskbench.cli.commands.task.get_client")
def test_zero_result_hint_filtered_empty_table_mode(mock_get_client):
    """Filtered-empty emits info message with pre-filter count in table mode."""
    mock_client = AsyncMock()
    tasks = [
        _make_task_b49(f"t{i}", f"Task {i}", status=StatusInfo(status="complete", type="closed")) for i in range(5)
    ]
    mock_client.get_tasks.return_value = tasks
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "list", "--list-id", "L1", "--open-only"],
    )

    assert result.exit_code == 0
    combined = _strip_ansi(result.stdout + result.stderr)
    assert "0 tasks matched the active filters" in combined
    assert "5 tasks total" in combined


@patch("taskbench.cli.commands.task.get_client")
def test_zero_result_hint_json_mode_suppressed(mock_get_client):
    """In JSON mode, info-level hint is suppressed; only envelope on stdout."""
    mock_client = AsyncMock()
    tasks = [
        _make_task_b49(f"t{i}", f"Task {i}", status=StatusInfo(status="complete", type="closed")) for i in range(3)
    ]
    mock_client.get_tasks.return_value = tasks
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "list", "--list-id", "L1", "--open-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == {"data": [], "count": 0}
    assert "0 tasks matched" not in result.stdout


@patch("taskbench.cli.commands.task.get_client")
def test_zero_result_no_hint_when_unfiltered(mock_get_client):
    """Unfiltered empty list emits 'No tasks found' — no hint about filters."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "list", "--list-id", "L1"],
    )

    assert result.exit_code == 0
    combined = _strip_ansi(result.stdout + result.stderr)
    assert "0 tasks matched the active filters" not in combined


@patch("taskbench.cli.commands.task.get_client")
def test_zero_result_hint_task_search_with_filters(mock_get_client):
    """task search emits zero-result hint when filters are active."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task_b49("t1", "Alpha", status=StatusInfo(status="open")),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "search", "--query", "alpha", "--status", "closed", "--workspace-id", "W1"],
    )

    assert result.exit_code == 0
    combined = _strip_ansi(result.stdout + result.stderr)
    assert "0 tasks matched the active filters" in combined


@patch("taskbench.cli.commands.task.get_client")
def test_zero_result_hint_task_mine_with_filters(mock_get_client):
    """task mine emits zero-result hint when filters are active."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [
        _make_task_b49("t1", "My Task", status=StatusInfo(status="open")),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "mine", "--workspace-id", "W1", "--open-only"],
    )

    mock_client.search_tasks.return_value = [
        _make_task_b49("t1", "My Task", status=StatusInfo(status="open")),
    ]
    result = runner.invoke(
        app,
        ["--format", "table", "task", "mine", "--workspace-id", "W1", "--status", "nonexistent"],
    )

    assert result.exit_code == 0
    combined = _strip_ansi(result.stdout + result.stderr)
    assert "0 tasks matched the active filters" in combined


# =============================================================================
# task search --name-only (from backlog-49 item 4)
# =============================================================================


@patch("taskbench.cli.commands.task.get_client")
def test_name_only_filters_by_task_name(mock_get_client):
    """--name-only keeps only tasks whose name contains the query (case-insensitive)."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task_b49("t1", "Deploy API"),
        _make_task_b49("t2", "Write API docs"),
        _make_task_b49("t3", "Fix login bug"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "api", "--workspace-id", "W1", "--name-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    names = [t["name"] for t in data["data"]]
    assert "Deploy API" in names
    assert "Write API docs" in names
    assert "Fix login bug" not in names


@patch("taskbench.cli.commands.task.get_client")
def test_name_only_case_insensitive(mock_get_client):
    """--name-only matching is case-insensitive."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task_b49("t1", "URGENT Bug Fix"),
        _make_task_b49("t2", "urgent refactor"),
        _make_task_b49("t3", "Normal task"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "urgent", "--workspace-id", "W1", "--name-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2


@patch("taskbench.cli.commands.task.get_client")
def test_name_only_with_limit(mock_get_client):
    """--name-only + --limit: count reflects the filtered (then truncated) set."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [_make_task_b49(f"t{i}", f"Matching {i}") for i in range(10)]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "Matching", "--workspace-id", "W1", "--name-only", "--limit", "3"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3


# =============================================================================
# Due-date format consistency (from backlog-49 item 5)
# =============================================================================


@patch("taskbench.cli.commands.task.get_client")
def test_create_due_date_accepts_yyyy_mm_dd(mock_get_client):
    """task create --due-date 2026-07-01 sends epoch ms to the provider."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "2026-07-01"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    due_val = call_kwargs["due_date"]
    assert due_val == str(1782864000000)


@patch("taskbench.cli.commands.task.get_client")
def test_create_due_date_accepts_relative(mock_get_client):
    """task create --due-date 7d sends an epoch-ms in the recent past."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "7d"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    due_val = int(call_kwargs["due_date"])
    assert due_val > 0


@patch("taskbench.cli.commands.task.get_client")
def test_update_due_date_accepts_yyyy_mm_dd(mock_get_client):
    """task update --due-date 2026-07-01 sends epoch ms to the provider."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "2026-07-01"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    due_val = call_kwargs["due_date"]
    assert due_val == str(1782864000000)


@patch("taskbench.cli.commands.task.get_client")
def test_update_due_date_accepts_relative(mock_get_client):
    """task update --due-date 7d sends epoch ms."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "7d"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    due_val = int(call_kwargs["due_date"])
    assert due_val > 0


@patch("taskbench.cli.commands.task.get_client")
def test_update_due_date_accepts_epoch_ms(mock_get_client):
    """task update --due-date <epoch-ms> passes through unchanged."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "1782691200000"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    assert call_kwargs["due_date"] == "1782691200000"


@patch("taskbench.cli.commands.task.get_client")
def test_create_due_date_accepts_epoch_ms(mock_get_client):
    """task create --due-date <epoch-ms> passes through unchanged."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task_b49("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "1782691200000"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    assert call_kwargs["due_date"] == "1782691200000"


# =============================================================================
# --ids-only output mode (from polish-63)
# =============================================================================


def _make_task_p63(task_id: str, name: str = "T") -> Task:
    return Task(id=task_id, name=name, url=f"https://x/{task_id}")


class TestIdsOnlyCreate:
    @patch("taskbench.cli.commands.task.get_client")
    def test_single_create(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = _make_task_p63("abc123", "New")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "create", "New", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "abc123"

    @patch("taskbench.cli.commands.task.get_client")
    def test_batch_create(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.create_task.side_effect = [
            _make_task_p63("id1", "A"),
            _make_task_p63("id2", "B"),
        ]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "create", "A", "B", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert lines == ["id1", "id2"]

    @patch("taskbench.cli.commands.task.get_client")
    def test_ids_only_json_mode(self, mock_get_client: AsyncMock) -> None:
        """--ids-only prints plain IDs regardless of --format json."""
        mock_client = AsyncMock()
        mock_client.create_task.return_value = _make_task_p63("j1", "J")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["--format", "json", "task", "create", "J", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "j1"

    def test_ids_only_and_brief_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "create", "X", "--list-id", "L1", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyDone:
    @patch("taskbench.cli.commands.task.get_client")
    def test_single_done(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task_p63("d1", "Done")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "done", "d1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "d1"

    @patch("taskbench.cli.commands.task.get_client")
    def test_batch_done(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.side_effect = [
            _make_task_p63("d1"),
            _make_task_p63("d2"),
        ]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "done", "d1", "d2", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip().splitlines() == ["d1", "d2"]

    def test_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "done", "d1", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyClose:
    @patch("taskbench.cli.commands.task.get_client")
    def test_close_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task_p63("c1")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "close", "c1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "c1"


class TestIdsOnlyStart:
    @patch("taskbench.cli.commands.task.get_client")
    def test_start_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task_p63("s1")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "start", "s1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "s1"


class TestIdsOnlyPark:
    @patch("taskbench.cli.commands.task.get_client")
    def test_park_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task_p63("p1")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "park", "p1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "p1"


class TestIdsOnlyStatus:
    @patch("taskbench.cli.commands.task.get_client")
    def test_status_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task_p63("st1")
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "status", "st1", "complete", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "st1"

    def test_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "status", "st1", "complete", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyDelete:
    @patch("taskbench.cli.commands.task.get_client")
    def test_single_delete(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.delete_task.return_value = True
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "delete", "del1", "--force", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "del1"

    @patch("taskbench.cli.commands.task.get_client")
    def test_batch_delete(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.delete_task.return_value = True
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "delete", "del1", "del2", "--force", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip().splitlines() == ["del1", "del2"]


# =============================================================================
# Truncated envelope flag (from polish-63)
# =============================================================================


class TestTruncatedFlag:
    @patch("taskbench.cli.commands.task.get_client")
    def test_truncated_true_when_clipped(self, mock_get_client: AsyncMock) -> None:
        """When result count > limit, envelope has truncated: true."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [_make_task_p63(f"t{i}") for i in range(5)]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "list", "--list-id", "L1", "--limit", "3"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 3

    @patch("taskbench.cli.commands.task.get_client")
    def test_no_truncated_when_not_clipped(self, mock_get_client: AsyncMock) -> None:
        """When result count <= limit, truncated key is absent."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [_make_task_p63(f"t{i}") for i in range(3)]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "list", "--list-id", "L1", "--limit", "50"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "truncated" not in data
        assert data["count"] == 3

    @patch("taskbench.cli.commands.task.get_client")
    def test_truncated_on_search(self, mock_get_client: AsyncMock) -> None:
        """task search also emits truncated when clipped."""
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [_make_task_p63(f"t{i}") for i in range(10)]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "search", "--workspace-id", "W1", "--limit", "5"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 5

    @patch("taskbench.cli.commands.task.get_client")
    def test_truncated_on_mine(self, mock_get_client: AsyncMock) -> None:
        """task mine also emits truncated when clipped."""
        mock_client = AsyncMock()
        mock_client.get_user.return_value = User(id=42, username="e", email="e@x.com")
        mock_client.search_tasks.return_value = [_make_task_p63(f"t{i}") for i in range(5)]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "mine", "--workspace-id", "W1", "--limit", "3"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 3


# =============================================================================
# Help text assertions (from polish-63)
# =============================================================================


class TestHelpText:
    def test_list_stats_help_mentions_space_id(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["list", "stats", "--help"])
        assert result.exit_code == 0
        assert "use --space-id to narrow" in _plain_help(result)

    def test_brief_help_is_compact(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "list", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)
        assert "date_updated" in _plain_help(result)

    def test_brief_help_on_get(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "get", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_mine(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "mine", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_search(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "search", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_create(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "create", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_update(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "update", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_done(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "done", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_brief_help_on_status(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "status", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in _plain_help(result)

    def test_bulk_export_help_mentions_default_list(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["bulk", "export-tasks", "--help"])
        assert result.exit_code == 0
        assert "Defaults to the configured default list" in _plain_help(result)

    def test_task_group_help_mentions_comments(self) -> None:
        from .conftest import _plain_help

        result = runner.invoke(app, ["task", "--help"])
        assert result.exit_code == 0
        assert "comments" in _plain_help(result).lower()
        assert "taskbench task comments" in _plain_help(result)


# =============================================================================
# Comment.user optional (from polish-63)
# =============================================================================


class TestCommentUserOptional:
    def test_comment_without_user_is_valid(self) -> None:
        comment = Comment(id="c1", comment_text="hi", date="123")
        assert comment.user is None

    def test_comment_with_user_is_valid(self) -> None:
        comment = Comment(
            id="c1",
            comment_text="hi",
            date="123",
            user=User(id=1, username="u", email="u@x.com"),
        )
        assert comment.user is not None
        assert comment.user.username == "u"


def test_name_only_substring_match_includes_eval_style_names() -> None:
    """Lock down --name-only filtering against tricky names that contain the
    query as a substring inside a hyphenated token (e.g. 'agent-test-eval-7').

    The r9 eval reported one such task being excluded, which was almost
    certainly cross-agent race (the sibling create/delete window), not a CLI
    bug. This test pins the actual filter semantics so any regression
    surfaces immediately.
    """
    from unittest.mock import AsyncMock, Mock, patch

    mock_client = AsyncMock()
    mock_client.get_user.return_value = Mock(id=1, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [
        _make_task_b49("a", "agent-test-eval-7 update-flow"),
        _make_task_b49("b", "Test Task — Minimal"),
        _make_task_b49("c", "tEsTING the matcher"),
        _make_task_b49("d", "Unrelated work"),
        _make_task_b49("e", "contest entrant"),  # contains "test" as a substring
    ]

    def _ctx() -> AsyncMock:
        m = AsyncMock()
        m.__aenter__.return_value = mock_client
        return m

    with patch("taskbench.cli.commands.task.get_client") as mock_get_client:
        mock_get_client.return_value = _ctx()
        result = runner.invoke(
            app,
            ["task", "search", "--query", "test", "--workspace-id", "W1", "--name-only", "--brief"],
        )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = [t["name"] for t in data["data"]]
    # All four substring matches present (incl. the hyphenated/eval-style name and the case-insensitive one).
    assert "agent-test-eval-7 update-flow" in names
    assert "Test Task — Minimal" in names
    assert "tEsTING the matcher" in names
    assert "contest entrant" in names
    # And only the obvious non-match was dropped.
    assert "Unrelated work" not in names
    assert data["count"] == 4
