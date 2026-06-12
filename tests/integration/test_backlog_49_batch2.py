"""Tests for backlog-49 batch 2 features.

Covers:
- Item 1: list stats --sort activity (composite ranking)
- Item 2: export defaults to JSON
- Item 3: config alias as primary command name
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import Folder, Space, SpaceRef, StatusInfo, Task, Team
from clickup.core.models import List as ClickUpList

from .conftest import make_mock_ctx

runner = CliRunner()


# ── helpers ──────────────────────────────────────────────────────────────


def _space(*, id: str = "S1", name: str = "Engineering") -> Space:
    return Space(id=id, name=name, private=False, statuses=[], multiple_assignees=False)


def _team(*, id: str = "T1", name: str = "Acme") -> Team:
    return Team(id=id, name=name, color="#000", members=[])


def _list(*, id: str, name: str, task_count: int = 0) -> ClickUpList:
    return ClickUpList(id=id, name=name, task_count=task_count)


def _folder(*, id: str, name: str, space_id: str = "S1") -> Folder:
    return Folder(
        id=id,
        name=name,
        orderindex=0,
        override_statuses=False,
        hidden=False,
        space=SpaceRef(id=space_id),
        task_count="0",
    )


def _task(
    *,
    id: str,
    name: str,
    date_updated: str | None = None,
    status_type: str = "open",
    status_name: str = "open",
) -> Task:
    return Task(
        id=id,
        name=name,
        date_updated=date_updated,
        status=StatusInfo(status=status_name, type=status_type),
    )


def _build_client(
    *,
    teams: list[Team] | None = None,
    spaces: list[Space] | None = None,
    folders: list[Folder] | None = None,
    folderless_lists: list[ClickUpList] | None = None,
    folder_lists: dict[str, list[ClickUpList]] | None = None,
    tasks_by_list: dict[str, list[Task]] | None = None,
) -> AsyncMock:
    client = AsyncMock()
    client.get_teams.return_value = teams or [_team()]
    client.get_spaces.return_value = spaces or [_space()]
    client.get_space.return_value = (spaces or [_space()])[0]
    client.get_folders.return_value = folders or []
    client.get_folderless_lists.return_value = folderless_lists or []

    _folder_lists = folder_lists or {}

    async def _get_lists(folder_id: str) -> list[ClickUpList]:
        return _folder_lists.get(folder_id, [])

    client.get_lists.side_effect = _get_lists

    _tasks = tasks_by_list or {}

    async def _get_tasks(list_id: str, **kwargs) -> list[Task]:
        return _tasks.get(list_id, [])

    client.get_tasks.side_effect = _get_tasks
    return client


# =============================================================================
# Item 1 — list stats --sort activity (composite ranking)
# =============================================================================


class TestListStatsActivitySort:
    def test_activity_is_default_sort(self):
        """The default --sort is 'activity' (no explicit --sort needed)."""
        client = _build_client(
            folderless_lists=[
                _list(id="L1", name="Old"),
                _list(id="L2", name="New"),
            ],
            tasks_by_list={
                "L1": [_task(id="t1", name="A", date_updated="1600000000000")],
                "L2": [_task(id="t2", name="B", date_updated="1700000000000")],
            },
        )
        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        # More recently updated list first (default = activity)
        assert payload["data"][0]["id"] == "L2"
        assert payload["data"][1]["id"] == "L1"

    def test_activity_sort_tiebreaker_by_task_count(self):
        """When last_updated ties, larger list wins."""
        client = _build_client(
            folderless_lists=[
                _list(id="L1", name="Small"),
                _list(id="L2", name="Big"),
            ],
            tasks_by_list={
                # Same last_updated timestamp, different task counts
                "L1": [
                    _task(id="t1", name="A", date_updated="1700000000000"),
                ],
                "L2": [
                    _task(id="t2", name="B", date_updated="1700000000000"),
                    _task(id="t3", name="C", date_updated="1700000000000"),
                    _task(id="t4", name="D", date_updated="1699900000000"),
                ],
            },
        )
        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "activity"]
            )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        # Same last_updated => bigger list first
        assert payload["data"][0]["id"] == "L2"
        assert payload["data"][1]["id"] == "L1"

    def test_activity_sort_null_last_updated_always_last(self):
        """Lists with null last_updated sort after all dated lists."""
        client = _build_client(
            folderless_lists=[
                _list(id="L1", name="Empty"),
                _list(id="L2", name="Active"),
                _list(id="L3", name="AlsoEmpty"),
            ],
            tasks_by_list={
                "L1": [],
                "L2": [_task(id="t1", name="A", date_updated="1700000000000")],
                "L3": [],
            },
        )
        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "activity"]
            )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        # Active list first; both empty lists last (null last_updated)
        assert payload["data"][0]["id"] == "L2"
        null_ids = {row["id"] for row in payload["data"][1:]}
        assert null_ids == {"L1", "L3"}

    def test_activity_sort_help_text(self):
        """--help for stats includes 'activity' in --sort description."""
        result = runner.invoke(app, ["list", "stats", "--help"])
        assert result.exit_code == 0
        assert "activity" in result.stdout


# =============================================================================
# Item 2 — export defaults to JSON
# =============================================================================


class TestExportDefaultsJson:
    """Both bulk export-tasks and task export default to JSON format now."""

    @patch("clickup.cli.commands.bulk.get_client")
    def test_bulk_export_default_produces_json_file(self, mock_get_client):
        """bulk export-tasks with no --output-format writes tasks.json."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [Task(id="t1", name="One")]
        mock_get_client.return_value = make_mock_ctx(mock_client)

        # Don't pass --output or --format; defaults should produce tasks.json
        result = runner.invoke(app, ["bulk", "export-tasks", "--list-id", "L1"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["format"] == "json"
        assert data["output_file"] == "tasks.json"
        # Verify the file was created and contains valid JSON
        content = json.loads(Path("tasks.json").read_text())
        assert isinstance(content, list)
        Path("tasks.json").unlink(missing_ok=True)

    @patch("clickup.cli.commands.bulk.get_client")
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
        Path("tasks.csv").unlink(missing_ok=True)

    @patch("clickup.cli.commands.bulk.get_client")
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

    @patch("clickup.cli.commands.task.get_client")
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
        content = json.loads(Path("tasks.json").read_text())
        assert isinstance(content, list)
        Path("tasks.json").unlink(missing_ok=True)

    @patch("clickup.cli.commands.task.get_client")
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
        Path("tasks.csv").unlink(missing_ok=True)

    @patch("clickup.cli.commands.task.get_client")
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


# =============================================================================
# Item 3 — config alias as the primary command name
# =============================================================================


class TestConfigAlias:
    def test_alias_add(self):
        """config alias NAME LIST_ID adds an alias."""
        result = runner.invoke(app, ["config", "alias", "myalias", "12345"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["action"] == "added"
        assert data["alias"] == "myalias"
        assert data["list_id"] == "12345"

    def test_alias_remove(self):
        """config alias --remove NAME removes an alias."""
        runner.invoke(app, ["config", "alias", "myalias", "12345"])
        result = runner.invoke(app, ["config", "alias", "--remove", "myalias"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["action"] == "removed"
        assert data["alias"] == "myalias"

    def test_alias_remove_missing_errors(self):
        """Removing a non-existent alias exits 1."""
        result = runner.invoke(app, ["config", "alias", "--remove", "nonexistent"])
        assert result.exit_code == 1

    def test_alias_no_id_errors(self):
        """Adding an alias without a list_id exits 1."""
        result = runner.invoke(app, ["config", "alias", "myalias"])
        assert result.exit_code == 1
        assert "list_id" in result.output.lower()

    def test_alias_list_empty(self):
        """config alias with no args and no aliases returns empty envelope."""
        result = runner.invoke(app, ["config", "alias"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {"data": [], "count": 0}

    def test_alias_list_populated(self):
        """config alias with no args lists all configured aliases."""
        runner.invoke(app, ["config", "alias", "alpha", "111"])
        runner.invoke(app, ["config", "alias", "beta", "222"])
        result = runner.invoke(app, ["config", "alias"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 2
        aliases = {row["alias"] for row in data["data"]}
        assert aliases == {"alpha", "beta"}
        list_ids = {row["list_id"] for row in data["data"]}
        assert list_ids == {"111", "222"}

    def test_alias_list_table_mode(self):
        """config alias in table mode renders a table."""
        runner.invoke(app, ["config", "alias", "myalias", "12345"])
        result = runner.invoke(app, ["--format", "table", "config", "alias"])
        assert result.exit_code == 0
        assert "myalias" in result.stdout
        assert "12345" in result.stdout

    def test_alias_list_table_empty(self):
        """config alias in table mode with no aliases shows info message."""
        result = runner.invoke(app, ["--format", "table", "config", "alias"])
        assert result.exit_code == 0
        # info message in table mode goes to stdout
        assert "No aliases" in result.stdout or result.stdout.strip() == ""


class TestSetDefaultListBackCompat:
    """set-default-list still works as a hidden back-compat alias."""

    def test_set_default_list_still_works(self):
        """set-default-list add/remove still works."""
        result = runner.invoke(app, ["config", "set-default-list", "myalias", "12345"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["alias"] == "myalias"

        result = runner.invoke(app, ["config", "set-default-list", "--remove", "myalias"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["action"] == "removed"

    def test_set_default_list_hidden_from_help(self):
        """set-default-list does not appear in config --help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "alias" in result.stdout
        assert "set-default-list" not in result.stdout

    def test_alias_visible_in_help(self):
        """config alias appears in config --help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "alias" in result.stdout
