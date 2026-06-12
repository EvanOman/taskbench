"""Tests for task management commands."""

import json
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core import Config
from clickup.core.models import List as ClickUpList
from clickup.core.models import PriorityInfo, StatusInfo

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
    assert result.exit_code == 1
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
        result = runner.invoke(app, ["task", "export", "--list-id", "list123", "--output", f.name, "--format", "json"])

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
