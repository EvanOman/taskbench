"""Tests for list management commands.

Consolidates tests from the original test_list_commands.py, plus list tests
formerly in test_command_coverage.py and test_final_coverage.py.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from taskbench.cli import output
from taskbench.cli.main import app
from taskbench.cli.output import FormatChoice, set_format
from taskbench.core.config import Config
from taskbench.core.exceptions import ClickUpError
from taskbench.core.models import List as ClickUpList

from .conftest import make_mock_ctx

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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
async def test_list_show_in_space(mock_get_client, sample_lists):
    """Test showing lists in a space (folderless)."""
    mock_client = AsyncMock()
    mock_client.get_folderless_lists.return_value = sample_lists
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["--format", "table", "list", "show", "--space-id", "space123"])

    assert result.exit_code == 0
    assert "Todo List" in result.stdout


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
async def test_list_show_empty_folder(mock_get_client):
    """Test showing lists in an empty folder."""
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["list", "show", "--folder-id", "empty_folder"])

    assert result.exit_code == 0
    # Empty result renders an empty Lists table (no list names appear)
    assert "Todo List" not in result.stdout


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


@patch("taskbench.cli.commands.list.get_client")
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


# =============================================================================
# list commands — from test_command_coverage.py (sync tests)
# =============================================================================


@patch("taskbench.cli.commands.list.get_client")
def test_list_show_in_folder_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_lists.return_value = [ClickUpList(id="L1", name="Sprint", task_count=5)]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--folder-id", "F1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


@patch("taskbench.cli.commands.list.get_client")
def test_list_show_in_space_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_folderless_lists.return_value = [ClickUpList(id="L1", name="Sprint", task_count=5)]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--space-id", "S1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


def test_list_show_no_args_errors():
    result = runner.invoke(app, ["list", "show"])
    assert result.exit_code == 1


@patch("taskbench.cli.commands.list.get_client")
def test_list_get_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_list.return_value = ClickUpList(
        id="L1",
        name="Sprint",
        task_count=5,
        content="some content",
        orderindex=0,
    )
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "get", "--list-id", "L1"])
    assert result.exit_code == 0
    assert "Sprint" in result.output


@patch("taskbench.cli.commands.list.get_client")
def test_list_create_in_folder_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "create", "New", "--folder-id", "F1"])
    assert result.exit_code == 0


@patch("taskbench.cli.commands.list.get_client")
def test_list_create_in_space_sync(mock_get_client):
    mock_client = AsyncMock()
    mock_client.create_folderless_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "create", "New", "--space-id", "S1"])
    assert result.exit_code == 0


def test_list_create_no_parent_errors():
    result = runner.invoke(app, ["list", "create", "New"])
    assert result.exit_code == 1


# =============================================================================
# list error paths — from test_final_coverage.py
# =============================================================================


@patch("taskbench.cli.commands.list.get_client")
def test_list_show_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_lists.side_effect = ClickUpError("nope")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["list", "show", "--folder-id", "F1"])
    assert result.exit_code == 1


@patch("taskbench.cli.commands.list.get_client")
def test_list_create_with_all_fields(mock_get_client):
    """Exercise the create_list path with all option flags set."""
    mock_client = AsyncMock()
    mock_client.create_list.return_value = ClickUpList(id="L1", name="New", task_count=0)
    mock_get_client.return_value = make_mock_ctx(mock_client)

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


# ---------------------------------------------------------------------------
# list noun/verb aliases (issue #35 item 5)
# ---------------------------------------------------------------------------


class TestListAliases:
    """``list list`` and ``list ls`` should be registered commands."""

    def test_list_list_alias_registered(self):
        from taskbench.cli.commands.list import app as list_app

        command_names = [cmd.name for cmd in list_app.registered_commands]
        assert "list" in command_names

    def test_list_ls_alias_registered(self):
        from taskbench.cli.commands.list import app as list_app

        command_names = [cmd.name for cmd in list_app.registered_commands]
        assert "ls" in command_names

    def test_show_still_registered(self):
        from taskbench.cli.commands.list import app as list_app

        command_names = [cmd.name for cmd in list_app.registered_commands]
        assert "show" in command_names


# ---------------------------------------------------------------------------
# list show --space-id folderless-only info (issue #35 item 6)
# ---------------------------------------------------------------------------


class TestListShowSpaceIdInfo:
    """--space-id emits an info message about folderless-only semantics."""

    @pytest.fixture(autouse=True)
    def _reset_fmt(self):
        set_format(FormatChoice.table)
        yield
        set_format(FormatChoice.table)

    @pytest.fixture
    def capture_console(self, monkeypatch):
        from rich.console import Console as RConsole

        buf = StringIO()
        monkeypatch.setattr(output, "_console", RConsole(file=buf, force_terminal=False, width=200))
        return buf

    def test_space_id_info_message_json(self, capsys):
        """In JSON mode info-level messages are suppressed (render_message contract)."""
        from taskbench.cli.commands.list import list_lists

        set_format("json")

        mock_client = AsyncMock()
        mock_client.get_folderless_lists = AsyncMock(
            return_value=[ClickUpList(id="L1", name="Sprint 42", task_count=7)]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("taskbench.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id=None, space_id="S1")

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_space_id_info_message_table(self, capture_console, capsys):
        """In table mode the info message mentions 'discover hierarchy'."""
        from taskbench.cli.commands.list import list_lists

        mock_client = AsyncMock()
        mock_client.get_folderless_lists = AsyncMock(
            return_value=[ClickUpList(id="L1", name="Sprint 42", task_count=7)]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("taskbench.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id=None, space_id="S1")

        console_out = capture_console.getvalue()
        assert "folderless" in console_out.lower() or "discover hierarchy" in console_out.lower()

    def test_folder_id_no_info_message(self, capsys):
        """--folder-id does NOT emit the folderless info."""
        from taskbench.cli.commands.list import list_lists

        set_format("json")

        mock_client = AsyncMock()
        mock_client.get_lists = AsyncMock(return_value=[ClickUpList(id="L1", name="Sprint 42", task_count=7)])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("taskbench.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id="F1", space_id=None)

        captured = capsys.readouterr()
        assert "folderless" not in captured.err.lower()
