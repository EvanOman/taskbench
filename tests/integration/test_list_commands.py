"""Tests for list management commands."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.config import Config
from clickup.core.exceptions import ClickUpError
from clickup.core.models import List as ClickUpList

runner = CliRunner()


@pytest.fixture
def sample_lists():
    """Sample lists for testing."""
    lists = []
    for i, (name, count, due_date, archived) in enumerate(
        [("Todo List", 5, None, False), ("In Progress", 3, "2024-12-31", False), ("Done", 10, None, True)], 1
    ):
        list_item = Mock()
        list_item.id = f"list{i}"
        list_item.name = name
        list_item.task_count = count
        list_item.due_date = due_date
        list_item.archived = archived
        # Fix the closure issue with lambda
        list_item.__str__ = lambda n=name: n
        list_item.__repr__ = lambda n=name: f"List({n})"
        lists.append(list_item)
    return lists


@pytest.fixture
def sample_list_detail():
    """Sample detailed list for testing."""
    space = Mock()
    space.id = "space123"
    space.name = "Test Space"
    space.__str__ = lambda self: "Test Space"
    space.__repr__ = lambda self: "Space(Test Space)"
    space.get = lambda key, default=None: {"name": "Test Space", "id": "space123"}.get(key, default)

    folder = Mock()
    folder.id = "folder123"
    folder.name = "Test Folder"
    folder.__str__ = lambda self: "Test Folder"
    folder.__repr__ = lambda self: "Folder(Test Folder)"
    folder.get = lambda key, default=None: {"name": "Test Folder", "id": "folder123"}.get(key, default)

    list_detail = Mock()
    list_detail.id = "list123"
    list_detail.name = "Test List"
    list_detail.description = "A test list"
    list_detail.content = "A test list"
    list_detail.task_count = 7
    list_detail.orderindex = 1
    list_detail.due_date = None
    list_detail.start_date = None
    list_detail.archived = False
    list_detail.assignee = None
    list_detail.space = space
    list_detail.folder = folder
    list_detail.__str__ = lambda self: "Test List"
    list_detail.__repr__ = lambda self: "List(Test List)"
    return list_detail


@patch("clickup.cli.commands.list.get_client")
async def test_list_show_in_folder(mock_get_client, sample_lists):
    """Test showing lists in a folder."""
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = sample_lists
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["--format", "table", "list", "show", "--folder-id", "folder123"])

    assert result.exit_code == 0
    assert "Todo List" in result.stdout
    assert "In Progress" in result.stdout
    assert "Done" in result.stdout


@patch("clickup.cli.commands.list.get_client")
async def test_list_show_in_space(mock_get_client, sample_lists):
    """Test showing lists in a space (folderless)."""
    mock_client = AsyncMock()
    mock_client.get_folderless_lists.return_value = sample_lists
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["--format", "table", "list", "show", "--space-id", "space123"])

    assert result.exit_code == 0
    assert "Todo List" in result.stdout


@patch("clickup.cli.commands.list.get_client")
async def test_list_get_details(mock_get_client, sample_list_detail):
    """Test getting detailed list information."""
    mock_client = AsyncMock()
    mock_client.get_list.return_value = sample_list_detail

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["--format", "table", "list", "get", "--list-id", "list123"])

    assert result.exit_code == 0
    assert "Test List" in result.stdout
    assert "A test list" in result.stdout
    assert "7" in result.stdout  # task count


@patch("clickup.cli.commands.list.get_client")
async def test_list_create_in_folder(mock_get_client):
    """Test creating a list in a folder."""
    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="new_list", name="New List", task_count=0)

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(
        app,
        ["--format", "table", "list", "create", "New List", "--folder-id", "folder123", "--content", "A new test list"],
    )

    assert result.exit_code == 0
    # New behavior: list create renders the new list as a data envelope, not a success message.
    assert "New List" in result.stdout


@patch("clickup.cli.commands.list.get_client")
async def test_list_create_in_space(mock_get_client):
    """Test creating a folderless list in a space."""
    mock_client = AsyncMock()
    mock_client.create_folderless_list.return_value = ClickUpList(id="new_list", name="Folderless List", task_count=0)
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["--format", "table", "list", "create", "Folderless List", "--space-id", "space123"])

    assert result.exit_code == 0
    # New behavior: rendered list (not success message).
    assert "Folderless List" in result.stdout


def test_list_show_missing_params():
    """Test list show command without required parameters."""
    result = runner.invoke(app, ["list", "show"])
    assert result.exit_code != 0
    # render_error + hint write to stderr (CliRunner.stderr would capture it,
    # but mix_stderr=True merges both streams into .output).
    assert "folder-id" in result.output or "space-id" in result.output


def test_list_get_missing_id():
    """Test list get command without list ID."""
    result = runner.invoke(app, ["list", "get"])
    assert result.exit_code != 0
    assert "list-id" in result.output


def test_list_create_missing_params():
    """Test list create without required parameters."""
    result = runner.invoke(app, ["list", "create", "--name", "Test"])
    assert result.exit_code != 0


@patch("clickup.cli.commands.list.get_client")
async def test_list_show_empty_folder(mock_get_client):
    """Test showing lists in an empty folder."""
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["list", "show", "--folder-id", "empty_folder"])

    assert result.exit_code == 0
    # Empty result renders an empty Lists table (no list names appear)
    assert "Todo List" not in result.stdout


@patch("clickup.cli.commands.list.get_client")
async def test_list_get_not_found(mock_get_client):
    """Test getting non-existent list."""
    mock_client = AsyncMock()
    mock_client.get_list.side_effect = ClickUpError("List not found")

    # Create a new mock each time to avoid coroutine reuse
    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["list", "get", "--list-id", "nonexistent"])

    assert result.exit_code != 0
    assert "error" in result.output.lower() or "not found" in result.output.lower()


@patch("clickup.cli.commands.list.get_client")
async def test_list_create_with_all_options(mock_get_client):
    """Test creating a list with all available options."""
    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="feature_list", name="Feature List", task_count=0)

    # Create a new mock each time to avoid coroutine reuse
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
            "list",
            "create",
            "Feature List",
            "--folder-id",
            "folder123",
            "--content",
            "List for tracking features",
            "--due-date",
            "2024-12-31",
            "--priority",
            "3",
        ],
    )

    assert result.exit_code == 0
    # New behavior: rendered list (not success message).
    assert "Feature List" in result.stdout


def test_list_help():
    """Test list command help."""
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "show" in result.stdout
    assert "get" in result.stdout
    assert "create" in result.stdout


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point Config() at a throwaway file so tests don't clobber the real user config."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    return tmp_path


@patch("clickup.cli.commands.list.get_client")
async def test_list_get_resolves_alias(mock_get_client, sample_list_detail, isolated_config):
    """`list get` should resolve list aliases via Config.resolve_list_id, like `task list` does."""
    Config().set("default_lists", {"omegapoint": "list123"})

    mock_client = AsyncMock()
    mock_client.get_list.return_value = sample_list_detail

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["list", "get", "--list-id", "omegapoint"])

    assert result.exit_code == 0, result.stdout
    mock_client.get_list.assert_awaited_with("list123")


@patch("clickup.cli.commands.list.get_client")
async def test_list_get_respects_format_json(mock_get_client, isolated_config):
    """`list get` should emit valid JSON when `--format json` is set."""
    real_list = ClickUpList(id="list123", name="Test List", task_count=7)
    mock_client = AsyncMock()
    mock_client.get_list.return_value = real_list

    def create_mock_client():
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__.return_value = mock_client
        return ctx_mgr

    mock_get_client.side_effect = create_mock_client

    result = runner.invoke(app, ["--format", "json", "list", "get", "--list-id", "list123"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["id"] == "list123"
    assert payload["name"] == "Test List"
    assert payload["task_count"] == 7


@patch("clickup.cli.commands.list.get_client")
async def test_list_show_respects_format_json(mock_get_client, isolated_config):
    """`list show` should emit valid JSON when `--format json` is set."""
    real_lists = [
        ClickUpList(id="list1", name="Todo List", task_count=5),
        ClickUpList(id="list2", name="In Progress", task_count=3),
    ]
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = real_lists
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["--format", "json", "list", "show", "--folder-id", "folder123"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["count"] == 2
    assert {item["id"] for item in payload["data"]} == {"list1", "list2"}


@patch("clickup.cli.commands.list.get_client")
async def test_list_show_defaults_to_json(mock_get_client, isolated_config):
    """Without an explicit --format flag, the CLI defaults to JSON."""
    real_lists = [ClickUpList(id="list1", name="Todo List", task_count=5)]
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = real_lists
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["list", "show", "--folder-id", "folder123"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == "list1"
