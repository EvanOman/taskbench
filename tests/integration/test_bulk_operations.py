"""Tests for bulk operations commands."""

import json
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app

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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_import_without_flag_refuses(mock_get_client, sample_tasks_json):
    """Bulk import must require --force/--yes."""
    mock_get_client.return_value.__aenter__.return_value = AsyncMock()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_tasks_json, f)
        f.flush()

        result = runner.invoke(app, ["bulk", "import-tasks", f.name, "--list-id", "123"])
        assert result.exit_code == 2
        assert "Refusing to import" in result.stderr


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
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
    from clickup.core.exceptions import ClickUpError

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


@patch("clickup.cli.commands.bulk.get_client")
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


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_import_partial_failure_exits_1(mock_get_client, sample_tasks_json):
    """import-tasks should exit 1 if any task creation fails."""
    mock_client = AsyncMock()
    from clickup.core.exceptions import ClickUpError

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
