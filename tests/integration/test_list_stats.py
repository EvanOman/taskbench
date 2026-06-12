"""Tests for `clickup list stats` — per-list statistics command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import Folder, Space, SpaceRef, StatusInfo, Task, Team
from clickup.core.models import List as ClickUpList

from .conftest import make_mock_ctx

runner = CliRunner()


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
    """Build a mock client for list stats tests."""
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


# ---------------------------------------------------------------------------
# JSON shape and basic behaviour
# ---------------------------------------------------------------------------


class TestListStatsJson:
    def test_multiple_lists_across_folder_and_folderless(self):
        """Stats cover both folderless and folder lists."""
        client = _build_client(
            folderless_lists=[_list(id="L1", name="Inbox", task_count=3)],
            folders=[_folder(id="F1", name="Sprint")],
            folder_lists={"F1": [_list(id="L2", name="Sprint Board", task_count=5)]},
            tasks_by_list={
                "L1": [
                    _task(id="t1", name="Task A", date_updated="1700000000000", status_type="open"),
                    _task(id="t2", name="Task B", date_updated="1700100000000", status_type="closed"),
                    _task(id="t3", name="Task C", date_updated="1700200000000", status_type="open"),
                ],
                "L2": [
                    _task(id="t4", name="Task D", date_updated="1700300000000", status_type="open"),
                    _task(id="t5", name="Task E", date_updated="1700400000000", status_type="open"),
                ],
            },
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["count"] == 2
        ids = {row["id"] for row in payload["data"]}
        assert ids == {"L1", "L2"}

        # Verify counts
        l1 = next(r for r in payload["data"] if r["id"] == "L1")
        assert l1["task_count"] == 3
        assert l1["open_count"] == 2  # t2 is closed
        assert l1["last_updated"] is not None
        assert l1["space"] == "Engineering"

        l2 = next(r for r in payload["data"] if r["id"] == "L2")
        assert l2["task_count"] == 2
        assert l2["open_count"] == 2

    def test_sort_by_tasks(self):
        """--sort tasks orders by task_count descending."""
        client = _build_client(
            folderless_lists=[
                _list(id="L1", name="Few", task_count=2),
                _list(id="L2", name="Many", task_count=10),
            ],
            tasks_by_list={
                "L1": [
                    _task(id="t1", name="A", date_updated="1700000000000"),
                    _task(id="t2", name="B", date_updated="1700100000000"),
                ],
                "L2": [_task(id=f"t{i}", name=f"T{i}", date_updated=f"{1700000000000 + i * 1000}") for i in range(10)],
            },
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "tasks"]
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["data"][0]["id"] == "L2"
        assert payload["data"][1]["id"] == "L1"

    def test_sort_by_updated(self):
        """--sort updated orders by most recently updated first."""
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
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "updated"]
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["data"][0]["id"] == "L2"  # More recent
        assert payload["data"][1]["id"] == "L1"

    def test_empty_list_handling(self):
        """Lists with no tasks get task_count 0 and null last_updated, sorting last."""
        client = _build_client(
            folderless_lists=[
                _list(id="L1", name="Active", task_count=5),
                _list(id="L2", name="Empty", task_count=0),
            ],
            tasks_by_list={
                "L1": [_task(id="t1", name="A", date_updated="1700000000000")],
                "L2": [],
            },
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        # Empty list should sort last (updated sort, None < any timestamp)
        assert payload["data"][-1]["id"] == "L2"
        empty = payload["data"][-1]
        assert empty["task_count"] == 0
        assert empty["open_count"] == 0
        assert empty["last_updated"] is None

    def test_json_shape_matches_spec(self):
        """JSON output has the envelope shape: {data: [...], count: N}."""
        client = _build_client(
            folderless_lists=[_list(id="L1", name="A")],
            tasks_by_list={"L1": []},
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert "data" in payload
        assert "count" in payload
        row = payload["data"][0]
        for key in ("id", "name", "space", "task_count", "open_count", "last_updated"):
            assert key in row, f"Missing key: {key}"

    def test_no_lists_returns_empty(self):
        """Workspace with no lists yields empty data array."""
        client = _build_client(
            folderless_lists=[],
            folders=[],
            tasks_by_list={},
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload == {"data": [], "count": 0}


# ---------------------------------------------------------------------------
# Table mode
# ---------------------------------------------------------------------------


class TestListStatsTable:
    def test_table_escapes_brackets(self):
        """List names with Rich markup brackets must be escaped."""
        client = _build_client(
            folderless_lists=[_list(id="L1", name="[bug] Tracker")],
            tasks_by_list={"L1": [_task(id="t1", name="X", date_updated="1700000000000")]},
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "table", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        # The bracket name should appear (not be swallowed by Rich)
        assert "bug" in result.stdout
        assert "Tracker" in result.stdout


# ---------------------------------------------------------------------------
# --space-id scoping
# ---------------------------------------------------------------------------


class TestListStatsSpaceId:
    def test_space_id_limits_scope(self):
        """--space-id limits to one space instead of the full workspace."""
        client = _build_client(
            folderless_lists=[_list(id="L1", name="Only One")],
            tasks_by_list={"L1": [_task(id="t1", name="X", date_updated="1700000000000")]},
        )
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--space-id", "S1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["count"] == 1
        # When --space-id is used, get_teams/get_spaces should NOT be called
        client.get_teams.assert_not_called()


# ---------------------------------------------------------------------------
# Error path: task fetch failure is graceful
# ---------------------------------------------------------------------------


class TestListStatsTaskFetchError:
    def test_task_fetch_error_treated_as_empty(self):
        """If get_tasks fails for a list, treat it as 0 tasks (fallback to list.task_count)."""
        client = _build_client(
            folderless_lists=[_list(id="L1", name="Broken", task_count=42)],
        )
        # Override get_tasks to raise
        client.get_tasks.side_effect = Exception("API error")

        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        row = payload["data"][0]
        # Falls back to list.task_count when tasks can't be fetched
        assert row["task_count"] == 42
        assert row["open_count"] == 0
        assert row["last_updated"] is None


# ---------------------------------------------------------------------------
# help text
# ---------------------------------------------------------------------------


class TestListStatsHelp:
    def test_stats_in_help(self):
        """stats subcommand appears in `clickup list --help`."""
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.stdout


# =============================================================================
# Activity sort (from backlog-49 batch 2 item 1)
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
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(app, ["--format", "json", "list", "stats", "--workspace-id", "T1"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
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
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "activity"]
            )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
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
        from unittest.mock import patch

        with patch("clickup.cli.commands.list.get_client", return_value=make_mock_ctx(client)):
            result = runner.invoke(
                app, ["--format", "json", "list", "stats", "--workspace-id", "T1", "--sort", "activity"]
            )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["data"][0]["id"] == "L2"
        null_ids = {row["id"] for row in payload["data"][1:]}
        assert null_ids == {"L1", "L3"}

    def test_activity_sort_help_text(self):
        """--help for stats includes 'activity' in --sort description."""
        result = runner.invoke(app, ["list", "stats", "--help"])
        assert result.exit_code == 0
        assert "activity" in result.stdout
