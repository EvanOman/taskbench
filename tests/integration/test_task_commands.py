"""Tests for task management commands."""

import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import PriorityInfo, StatusInfo

runner = CliRunner()


@pytest.fixture
def sample_tasks():
    """Sample tasks for testing."""
    tasks = []
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
    assert "Created task" in result.stdout


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
    assert "Updated task" in result.stdout


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
    assert "Deleted task" in result.stdout


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
    assert "Deleted task" in result.stdout


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
    assert "Updated task status" in result.stdout
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


@patch("clickup.cli.commands.task.get_client")
def test_task_status_change_positional(mock_get_client):
    """`task status TASK_ID STATUS` positional form works."""
    mock_client, factory = _status_mock_client()
    mock_get_client.side_effect = factory

    result = runner.invoke(app, ["task", "status", "task123", "in progress"])

    assert result.exit_code == 0
    assert "Updated task status" in result.stdout
    mock_client.update_task.assert_awaited_once_with("task123", status="in progress")


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


def test_task_list_missing_list_id():
    """Test task list without list ID."""
    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code != 0
    assert "list" in result.stdout.lower() or "workspace" in result.stdout.lower()


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


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plain_field_no_reverse(mock_get_client, sample_tasks):
    """`--sort updated` → order_by=updated, no reverse."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated"])
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert "reverse" not in kwargs


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plain_field_with_reverse(mock_get_client, sample_tasks):
    """Back-compat: `--sort updated --reverse` → order_by=updated, reverse=true."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(
        app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated", "--reverse"]
    )
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert kwargs.get("reverse") == "true"


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_colon_desc(mock_get_client, sample_tasks):
    """`--sort updated:desc` → descending."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:desc"])
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert kwargs.get("reverse") == "true"


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_colon_asc(mock_get_client, sample_tasks):
    """`--sort updated:asc` → ascending."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "updated:asc"])
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert "reverse" not in kwargs


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_minus_prefix(mock_get_client, sample_tasks):
    """`--sort -updated` → descending (git/jq style)."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "-updated"])
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert kwargs.get("reverse") == "true"


@patch("clickup.cli.commands.task.get_client")
def test_task_list_sort_plus_prefix(mock_get_client, sample_tasks):
    """`--sort +updated` → ascending."""
    mock_client = _sort_list_mock(mock_get_client, sample_tasks)
    result = runner.invoke(app, ["--format", "table", "task", "list", "--list-id", "L", "--sort", "+updated"])
    assert result.exit_code == 0
    kwargs = mock_client.get_tasks.await_args.kwargs
    assert kwargs.get("order_by") == "updated"
    assert "reverse" not in kwargs


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
    assert "No tasks found" in result.stdout or len(result.stdout.strip()) == 0


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
    assert "Created task" in result.stdout


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
        assert "Exported" in result.stdout


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
