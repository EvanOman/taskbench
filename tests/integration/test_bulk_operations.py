"""Tests for bulk operations commands.

Consolidates tests from the original test_bulk_operations.py, plus bulk tests
formerly in test_command_coverage.py, test_final_coverage.py, and
test_more_coverage.py.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from taskbench.cli.main import app
from taskbench.core.exceptions import ClickUpError
from taskbench.core.models import Assignee, PriorityInfo, StatusInfo, Task

from .conftest import make_mock_ctx

runner = CliRunner()


@pytest.fixture
def sample_tasks_csv():
    """Sample CSV data for testing."""
    return """name,description,priority,status
Test Task 1,First test task,high,to do
Test Task 2,Second test task,medium,in progress
Test Task 3,Third test task,low,complete"""


@pytest.fixture
def sample_tasks_json():
    """Sample JSON data for testing."""
    return [
        {"name": "Test Task 1", "description": "First test task", "priority": "high", "status": "to do"},
        {"name": "Test Task 2", "description": "Second test task", "priority": "medium", "status": "in progress"},
        {"name": "Test Task 3", "description": "Third test task", "priority": "low", "status": "complete"},
    ]


def create_task_mocks(sample_tasks_json):
    """Create properly structured task mocks."""
    task_mocks = []
    for task in sample_tasks_json:
        task_mock = Mock()
        task_mock.id = f"task_{task['name']}"
        task_mock.name = task["name"]
        task_mock.description = task["description"]
        task_mock.status = Mock(status=task["status"])
        task_mock.priority = Mock(priority=task["priority"])
        task_mock.assignees = []
        task_mock.due_date = None
        task_mock.date_created = None
        task_mock.date_updated = None
        task_mock.url = None

        # Add model_dump method for JSON export
        def model_dump(task_data=task, current_task_mock=task_mock):
            return {
                "id": current_task_mock.id,
                "name": current_task_mock.name,
                "description": current_task_mock.description,
                "status": {"status": task_data["status"]},
                "priority": {"priority": task_data["priority"]},
                "assignees": [],
                "due_date": None,
                "date_created": None,
                "date_updated": None,
                "url": None,
            }

        task_mock.model_dump = model_dump
        task_mocks.append(task_mock)

    return task_mocks


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_export_csv(mock_get_client, sample_tasks_json):
    """Test bulk export to CSV format."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = create_task_mocks(sample_tasks_json)

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "123", "--format", "csv", "--output", f.name])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {"exported": 3, "output_file": f.name, "format": "csv"}


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_export_json(mock_get_client, sample_tasks_json):
    """Test bulk export to JSON format."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = create_task_mocks(sample_tasks_json)

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "123", "--format", "json", "--output", f.name],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {"exported": 3, "output_file": f.name, "format": "json"}


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_csv_dry_run(mock_get_client, sample_tasks_csv):
    """Test bulk import from CSV with dry run."""
    mock_client = AsyncMock()
    mock_get_client.return_value.__aenter__.return_value = mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(sample_tasks_csv)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123", "--dry-run"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert data["would_create"] == 3
        assert len(data["tasks"]) == 3


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_json_actual(mock_get_client, sample_tasks_json):
    """Test bulk import from JSON with actual creation."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Mock(id="task123")

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123", "--yes"])

        assert result.exit_code == 0
        # New behavior: structured counts envelope (render_kv), not a success message.
        assert '"created": 3' in result.stdout
        assert '"failed": 0' in result.stdout


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_without_flag_refuses(mock_get_client, sample_tasks_json):
    """Bulk import must require --force/--yes."""
    mock_get_client.return_value.__aenter__.return_value = AsyncMock()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123"])
        assert result.exit_code == 2
        assert "Refusing to import" in result.stderr


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_without_flag_refuses(mock_get_client):
    """Bulk update must require --force/--yes."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "1"
    task_mock.name = "T"
    task_mock.status = Mock(status="to do")
    task_mock.priority = Mock(priority="medium")
    mock_client.get_tasks.return_value = [task_mock]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "123", "--status", "in progress"])
    assert result.exit_code == 2
    assert "Refusing to update" in result.stderr


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_tasks(mock_get_client):
    """Test bulk update of tasks."""
    mock_client = AsyncMock()
    mock_tasks = []
    for i, status in enumerate(["to do", "to do"], 1):
        task_mock = Mock()
        task_mock.id = str(i)
        task_mock.name = f"Task {i}"
        task_mock.status = Mock(status=status)
        task_mock.priority = Mock(priority="medium")
        mock_tasks.append(task_mock)
    mock_client.get_tasks.return_value = mock_tasks
    mock_client.update_task.return_value = Mock(id="1")

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "123", "--status", "in progress", "--yes"])

    assert result.exit_code == 0
    # New behavior: structured counts envelope, not a success message.
    assert '"updated": 2' in result.stdout
    assert '"failed": 0' in result.stdout


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_with_filter(mock_get_client):
    """Test bulk update with status filter."""
    mock_client = AsyncMock()
    mock_tasks = []
    for i, (status, priority) in enumerate([("to do", "high"), ("in progress", "low")], 1):
        task_mock = Mock()
        task_mock.id = str(i)
        task_mock.name = f"Task {i}"
        task_mock.status = Mock(status=status)
        task_mock.priority = Mock(priority=priority)
        mock_tasks.append(task_mock)
    mock_client.get_tasks.return_value = mock_tasks
    mock_client.update_task.return_value = Mock(id="1")

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        ["bulk", "bulk-update", "--list-id", "123", "--filter-status", "to do", "--priority", "1", "--yes"],
    )

    assert result.exit_code == 0
    # Should only update tasks with "to do" status
    mock_client.update_task.assert_called()


def test_bulk_export_no_list():
    """Test bulk export without list ID."""
    result = runner.invoke(app, ["bulk", "export-tasks"])
    assert result.exit_code != 0
    assert "list-id" in result.output.lower()


def test_bulk_import_invalid_file():
    """Test bulk import with invalid file."""
    result = runner.invoke(app, ["bulk", "import-tasks", "--list-id", "123", "--file", "nonexistent.csv"])
    assert result.exit_code != 0


def test_bulk_import_invalid_format():
    """Test bulk import with invalid file format."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("invalid content")
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", "--list-id", "123", "--file", f.name])
        assert result.exit_code != 0


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_dry_run_json_shape(mock_get_client, sample_tasks_json):
    """import-tasks --dry-run JSON shape: {dry_run, would_create, tasks}."""
    mock_client = AsyncMock()
    mock_get_client.return_value.__aenter__.return_value = mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123", "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert data["would_create"] == 3
        assert isinstance(data["tasks"], list)


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_dry_run_json_shape(mock_get_client):
    """bulk-update --dry-run JSON shape: {dry_run, would_update, updates, tasks}."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "1"
    task_mock.name = "T"
    task_mock.status = Mock(status="to do")
    task_mock.priority = Mock(priority="medium")
    mock_client.get_tasks.return_value = [task_mock]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "123", "--status", "done", "--dry-run"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert data["would_update"] == 1
    assert data["updates"]["status"] == "done"
    assert data["tasks"][0]["id"] == "1"


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_dry_run_table_mode(mock_get_client):
    """bulk-update --dry-run --format table shows the preview table."""
    mock_client = AsyncMock()
    task_mock = Mock()
    task_mock.id = "1"
    task_mock.name = "MyTask"
    task_mock.status = Mock(status="to do")
    task_mock.priority = Mock(priority="medium")
    mock_client.get_tasks.return_value = [task_mock]

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app, ["--format", "table", "bulk", "bulk-update", "--list-id", "123", "--status", "done", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "MyTask" in result.output
    assert "Bulk Update Preview" in result.output


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_deterministic_order(mock_get_client):
    """Updated tasks should be processed in input order (deterministic output)."""
    mock_client = AsyncMock()
    # Create 5 tasks with distinct IDs
    mock_tasks = []
    for i in range(5):
        t = Mock()
        t.id = str(i)
        t.name = f"Task {i}"
        t.status = Mock(status="to do")
        t.priority = Mock(priority="medium")
        mock_tasks.append(t)
    mock_client.get_tasks.return_value = mock_tasks
    # Track the order of update_task calls
    call_ids: list[str] = []

    async def track_update(task_id, **kwargs):
        call_ids.append(task_id)
        return Mock(id=task_id)

    mock_client.update_task.side_effect = track_update

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "123", "--status", "done", "--yes"])
    assert result.exit_code == 0
    assert '"updated": 5' in result.stdout
    assert '"failed": 0' in result.stdout
    # All 5 tasks should have been updated
    assert len(call_ids) == 5


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_partial_failure(mock_get_client):
    """Partial failures should be aggregated; exit 1 if any failed."""
    mock_client = AsyncMock()
    mock_tasks = []
    for i in range(3):
        t = Mock()
        t.id = str(i)
        t.name = f"Task {i}"
        t.status = Mock(status="to do")
        t.priority = Mock(priority="medium")
        mock_tasks.append(t)
    mock_client.get_tasks.return_value = mock_tasks

    # Second task fails
    from taskbench.core.exceptions import ClickUpError

    async def partial_fail_update(task_id, **kwargs):
        if task_id == "1":
            raise ClickUpError("Simulated failure")
        return Mock(id=task_id)

    mock_client.update_task.side_effect = partial_fail_update

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "123", "--status", "done", "--yes"])
    assert result.exit_code == 1
    assert '"updated": 2' in result.stdout
    assert '"failed": 1' in result.stdout
    # Failure warning should appear on stderr
    assert "Simulated failure" in result.stderr


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_parallel_creation(mock_get_client, sample_tasks_json):
    """import-tasks should create tasks in parallel batches."""
    mock_client = AsyncMock()
    call_count = 0

    async def count_creates(list_id, **kwargs):
        nonlocal call_count
        call_count += 1
        return Mock(id=f"task_{call_count}")

    mock_client.create_task.side_effect = count_creates

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123", "--yes", "--batch-size", "2"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["created"] == 3
        assert data["failed"] == 0
    assert call_count == 3


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_partial_failure_exits_1(mock_get_client, sample_tasks_json):
    """import-tasks should exit 1 if any task creation fails."""
    mock_client = AsyncMock()
    from taskbench.core.exceptions import ClickUpError

    call_idx = 0

    async def fail_second(list_id, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 2:
            raise ClickUpError("creation failed")
        return Mock(id=f"task_{call_idx}")

    mock_client.create_task.side_effect = fail_second

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123", "--yes"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["created"] == 2
        assert data["failed"] == 1


# =============================================================================
# bulk — from test_command_coverage.py
# =============================================================================


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_export_csv_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name, "--format", "csv"],
        )
    assert result.exit_code == 0


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_dry_run_no_force_required(mock_get_client):
    """--dry-run should not require --force."""
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([{"name": "t1"}, {"name": "t2"}], f)
        f.flush()
        result = runner.invoke(
            app,
            ["bulk", "import-tasks", f.name, "--list-id", "L1", "--dry-run"],
        )
    assert result.exit_code == 0


# =============================================================================
# bulk error paths — from test_final_coverage.py and test_more_coverage.py
# =============================================================================


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_unsupported_xml_format(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write("<x/>")
        f.flush()
        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "L1"])
    assert result.exit_code == 1
    assert "Unsupported" in result.output or "format" in result.output.lower()


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_import_empty_file(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        f.flush()
        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "L1"])
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_export_unsupported_format(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name, "--format", "xml"],
        )
    assert result.exit_code == 1


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_dry_run_sync(mock_get_client):
    mock_client = AsyncMock()
    task = Mock()
    task.id = "t1"
    task.name = "X"
    task.status = Mock(status="todo")
    task.priority = Mock(priority="medium")
    mock_client.get_tasks.return_value = [task]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1", "--status", "done", "--dry-run"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert data["would_update"] == 1


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_export_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = ClickUpError("nope")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name],
        )
    assert result.exit_code == 1
    assert "nope" in result.stderr


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_no_updates_specified(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1"])
    assert result.exit_code == 1
    assert "at least one update" in result.stderr.lower()


@patch("taskbench.cli.commands.bulk.get_client")
def test_bulk_update_no_matches_warns(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1", "--status", "done", "--yes"])
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# --all-lists bulk-update (issue #35 item 4)
# ---------------------------------------------------------------------------


def _bulk_task(**kw: Any) -> Task:
    base: dict[str, Any] = {
        "id": "task42",
        "name": "Ship the thing",
        "description": "A description",
        "status": StatusInfo(status="open"),
        "priority": PriorityInfo(priority="2", id="2"),
        "assignees": [Assignee(id=1, username="evan")],
        "date_created": "1700000000000",
        "date_updated": "1700100000000",
        "due_date": "1700500000000",
    }
    base.update(kw)
    return Task(**base)


def _mock_config_with_lists(aliases: dict[str, str] | None) -> MagicMock:
    """Build a MagicMock Config whose .get("default_lists") returns *aliases*."""

    def _get(key: str, default: Any = None) -> Any:
        if key == "default_lists":
            return aliases
        return default

    return MagicMock(get=_get, resolve_list_id=lambda v: v)


class TestBulkUpdateAllLists:
    """--all-lists iterates configured aliases; dry-run and failure-continuation work."""

    def _make_mock_client(self, tasks_by_list: dict[str, list[Task]]) -> AsyncMock:
        client = AsyncMock()

        async def get_tasks(list_id: str, **kw: Any) -> list[Task]:
            return tasks_by_list.get(list_id, [])

        client.get_tasks = get_tasks
        client.update_task = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    _TWO_LISTS = {"inbox": "list_a", "active": "list_b"}

    def test_all_lists_dry_run(self, tmp_path, capsys):
        """--all-lists --dry-run previews tasks across multiple lists."""
        from taskbench.cli.commands.bulk import bulk_update

        tasks_a = [_bulk_task(id="t1", name="Task A")]
        tasks_b = [_bulk_task(id="t2", name="Task B")]
        client = self._make_mock_client({"list_a": tasks_a, "list_b": tasks_b})

        with (
            patch("taskbench.cli.commands.bulk.get_client", return_value=client),
            patch("taskbench.cli.shared.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
        ):
            bulk_update(
                list_id=None,
                all_lists=True,
                filter_status=None,
                new_status="in progress",
                new_priority=None,
                new_assignee=None,
                dry_run=True,
                force=False,
            )

        out = capsys.readouterr().out
        assert "dry run" in out.lower() or "Task A" in out

    def test_all_lists_force_updates(self, tmp_path, capsys):
        """--all-lists --force actually applies updates across lists."""
        from taskbench.cli.commands.bulk import bulk_update

        tasks_a = [_bulk_task(id="t1", name="Task A")]
        tasks_b = [_bulk_task(id="t2", name="Task B")]
        client = self._make_mock_client({"list_a": tasks_a, "list_b": tasks_b})

        with (
            patch("taskbench.cli.commands.bulk.get_client", return_value=client),
            patch("taskbench.cli.shared.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
        ):
            bulk_update(
                list_id=None,
                all_lists=True,
                filter_status=None,
                new_status="done",
                new_priority=None,
                new_assignee=None,
                dry_run=False,
                force=True,
            )

        assert client.update_task.call_count == 2

    def test_all_lists_refuses_without_force(self, tmp_path, capsys):
        """Without --force, exits 2."""
        import typer as _typer

        from taskbench.cli.commands.bulk import bulk_update

        tasks_a = [_bulk_task(id="t1", name="Task A")]
        client = self._make_mock_client({"list_a": tasks_a})

        with (
            patch("taskbench.cli.commands.bulk.get_client", return_value=client),
            patch("taskbench.cli.shared.Config", return_value=_mock_config_with_lists({"inbox": "list_a"})),
            pytest.raises(_typer.Exit) as exc_info,
        ):
            bulk_update(
                list_id=None,
                all_lists=True,
                filter_status=None,
                new_status="done",
                new_priority=None,
                new_assignee=None,
                dry_run=False,
                force=False,
            )

        assert exc_info.value.exit_code == 2

    def test_all_lists_no_aliases_errors(self, capsys):
        """--all-lists with no configured aliases is a usage error (exit 2)."""
        import typer as _typer

        from taskbench.cli.commands.bulk import bulk_update

        with (
            patch("taskbench.cli.shared.Config", return_value=_mock_config_with_lists(None)),
            pytest.raises(_typer.Exit) as exc_info,
        ):
            bulk_update(
                list_id=None,
                all_lists=True,
                filter_status=None,
                new_status="done",
                new_priority=None,
                new_assignee=None,
                dry_run=False,
                force=True,
            )

        assert exc_info.value.exit_code == 2

    def test_all_lists_continues_through_per_list_failure(self, capsys):
        """Per-list fetch failure doesn't abort remaining lists."""
        from taskbench.cli.commands.bulk import bulk_update

        tasks_b = [_bulk_task(id="t2", name="Task B")]
        client = AsyncMock()

        async def get_tasks(list_id: str, **kw: Any) -> list[Task]:
            if list_id == "list_a":
                raise ClickUpError("API error")
            return tasks_b

        client.get_tasks = get_tasks
        client.update_task = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("taskbench.cli.commands.bulk.get_client", return_value=client),
            patch("taskbench.cli.shared.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
        ):
            bulk_update(
                list_id=None,
                all_lists=True,
                filter_status=None,
                new_status="done",
                new_priority=None,
                new_assignee=None,
                dry_run=False,
                force=True,
            )

        # list_a failed but list_b's task was still updated
        assert client.update_task.call_count == 1


# =============================================================================
# Export defaults to JSON (from backlog-49 batch 2 item 2)
# =============================================================================


class TestExportDefaultsJson:
    """Both bulk export-tasks and task export default to JSON format now."""

    @patch("taskbench.cli.commands.bulk.get_client")
    def test_bulk_export_default_produces_json_file(self, mock_get_client):
        """bulk export-tasks with no --output-format writes tasks.json."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "L1"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "json"
        assert data["output_file"] == "tasks.json"
        from pathlib import Path

        content = json.loads(Path("tasks.json").read_text())
        assert isinstance(content, list)
        Path("tasks.json").unlink(missing_ok=True)

    @patch("taskbench.cli.commands.bulk.get_client")
    def test_bulk_export_csv_explicit_produces_csv_file(self, mock_get_client):
        """bulk export-tasks --format csv without --output produces tasks.csv."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "L1", "--format", "csv"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "csv"
        assert data["output_file"] == "tasks.csv"
        from pathlib import Path

        Path("tasks.csv").unlink(missing_ok=True)

    @patch("taskbench.cli.commands.bulk.get_client")
    def test_bulk_export_explicit_output_respected(self, mock_get_client):
        """--output overrides the default filename."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        mock_get_client.return_value = make_mock_ctx(mock_client)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["output_file"] == f.name

    @patch("taskbench.cli.commands.task.get_client")
    def test_task_export_default_produces_json_file(self, mock_get_client):
        """task export with no --output produces tasks.json."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "export", "--list-id", "L1"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "json"
        assert data["output_file"] == "tasks.json"
        from pathlib import Path

        content = json.loads(Path("tasks.json").read_text())
        assert isinstance(content, list)
        Path("tasks.json").unlink(missing_ok=True)

    @patch("taskbench.cli.commands.task.get_client")
    def test_task_export_csv_produces_csv_file(self, mock_get_client):
        """task export --output-format csv without --output produces tasks.csv."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        result = runner.invoke(app, ["task", "export", "--list-id", "L1", "--output-format", "csv"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "csv"
        assert data["output_file"] == "tasks.csv"
        from pathlib import Path

        Path("tasks.csv").unlink(missing_ok=True)

    @patch("taskbench.cli.commands.task.get_client")
    def test_task_export_explicit_output_respected(self, mock_get_client):
        """--output overrides the default filename for task export."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        mock_get_client.return_value = make_mock_ctx(mock_client)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            result = runner.invoke(app, ["task", "export", "--list-id", "L1", "--output", f.name])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["output_file"] == f.name
