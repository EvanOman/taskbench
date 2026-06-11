"""Unit tests for ``_apply_task_filters`` and the ``task search`` filter flags.

These pin the shared filter pipeline's contract directly, then exercise the
new search flags via CliRunner against mocked providers.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.commands.task import _apply_task_filters
from clickup.cli.main import app
from clickup.core.models import PriorityInfo, StatusInfo, Task

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(client: AsyncMock) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


def _make_task(
    task_id: str,
    name: str,
    status: str = "to do",
    status_type: str = "open",
    priority: str | None = None,
    date_updated: str = "1700000001000",
) -> Mock:
    """Build a lightweight mock task for filter tests."""
    t = Mock()
    t.id = task_id
    t.name = name
    t.status = StatusInfo(status=status, type=status_type)
    t.priority = PriorityInfo(priority=priority) if priority else None
    t.date_created = date_updated
    t.date_updated = date_updated
    t.due_date = None
    t.assignees = []
    t.description = ""
    return t


# ---------------------------------------------------------------------------
# _apply_task_filters unit tests
# ---------------------------------------------------------------------------


class TestApplyTaskFiltersStatus:
    def test_filters_by_status(self):
        tasks = [
            _make_task("1", "A", status="to do"),
            _make_task("2", "B", status="in progress"),
            _make_task("3", "C", status="complete"),
        ]
        result = _apply_task_filters(tasks, statuses={"to do"})
        assert [t.id for t in result] == ["1"]

    def test_status_filter_is_case_insensitive(self):
        tasks = [_make_task("1", "A", status="In Progress")]
        result = _apply_task_filters(tasks, statuses={"in progress"})
        assert [t.id for t in result] == ["1"]

    def test_multiple_statuses(self):
        tasks = [
            _make_task("1", "A", status="to do"),
            _make_task("2", "B", status="in progress"),
            _make_task("3", "C", status="complete"),
        ]
        result = _apply_task_filters(tasks, statuses={"to do", "complete"})
        assert {t.id for t in result} == {"1", "3"}

    def test_none_statuses_no_filter(self):
        tasks = [_make_task("1", "A"), _make_task("2", "B")]
        result = _apply_task_filters(tasks, statuses=None)
        assert len(result) == 2


class TestApplyTaskFiltersUpdatedSince:
    def test_filters_by_updated_since(self):
        tasks = [
            _make_task("1", "Old", date_updated="1000"),
            _make_task("2", "New", date_updated="2000"),
        ]
        result = _apply_task_filters(tasks, updated_since_ms=1500)
        assert [t.id for t in result] == ["2"]

    def test_none_updated_since_no_filter(self):
        tasks = [_make_task("1", "A"), _make_task("2", "B")]
        result = _apply_task_filters(tasks, updated_since_ms=None)
        assert len(result) == 2


class TestApplyTaskFiltersOpenOnly:
    def test_open_only_drops_closed(self):
        tasks = [
            _make_task("1", "Open", status="to do", status_type="open"),
            _make_task("2", "Closed", status="complete", status_type="closed"),
        ]
        result = _apply_task_filters(tasks, open_only=True)
        assert [t.id for t in result] == ["1"]

    def test_open_only_false_keeps_all(self):
        tasks = [
            _make_task("1", "Open", status="to do", status_type="open"),
            _make_task("2", "Closed", status="complete", status_type="closed"),
        ]
        result = _apply_task_filters(tasks, open_only=False)
        assert len(result) == 2


class TestApplyTaskFiltersSort:
    def test_sorts_by_priority_asc(self):
        tasks = [
            _make_task("1", "Low", priority="4"),
            _make_task("2", "Urgent", priority="1"),
            _make_task("3", "High", priority="2"),
        ]
        result = _apply_task_filters(tasks, sort_field="priority", sort_descending=False)
        assert [t.id for t in result] == ["2", "3", "1"]

    def test_sorts_by_priority_desc(self):
        tasks = [
            _make_task("1", "Low", priority="4"),
            _make_task("2", "Urgent", priority="1"),
        ]
        result = _apply_task_filters(tasks, sort_field="priority", sort_descending=True)
        assert [t.id for t in result] == ["1", "2"]

    def test_sorts_by_updated(self):
        tasks = [
            _make_task("1", "Old", date_updated="3000"),
            _make_task("2", "New", date_updated="1000"),
        ]
        result = _apply_task_filters(tasks, sort_field="updated", sort_descending=False)
        assert [t.id for t in result] == ["2", "1"]

    def test_none_sort_preserves_order(self):
        tasks = [_make_task("1", "A"), _make_task("2", "B")]
        result = _apply_task_filters(tasks, sort_field=None)
        assert [t.id for t in result] == ["1", "2"]


class TestApplyTaskFiltersCombined:
    def test_status_then_sort(self):
        tasks = [
            _make_task("1", "A", status="to do", priority="3"),
            _make_task("2", "B", status="in progress", priority="1"),
            _make_task("3", "C", status="to do", priority="1"),
        ]
        result = _apply_task_filters(tasks, statuses={"to do"}, sort_field="priority", sort_descending=False)
        assert [t.id for t in result] == ["3", "1"]

    def test_all_filters_combined(self):
        tasks = [
            _make_task("1", "Old open", status="to do", status_type="open", date_updated="500"),
            _make_task("2", "New open", status="to do", status_type="open", date_updated="2000"),
            _make_task("3", "New closed", status="complete", status_type="closed", date_updated="2000"),
            _make_task("4", "New progress", status="in progress", status_type="custom", date_updated="2000"),
        ]
        result = _apply_task_filters(
            tasks,
            statuses={"to do", "in progress"},
            updated_since_ms=1000,
            open_only=True,
        )
        # Old open (#1) filtered by updated_since. Closed (#3) filtered by open_only.
        # Only #2 (to do) and #4 (in progress) survive.
        assert {t.id for t in result} == {"2", "4"}


# ---------------------------------------------------------------------------
# task search CLI integration tests (via mocked client)
# ---------------------------------------------------------------------------


class TestSearchOptionalQuery:
    @patch("clickup.cli.commands.task.get_client")
    def test_bare_search_enumerates_all(self, mock_get_client):
        """Omitting --query returns all tasks (empty string query)."""
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [Task(id="t1", name="All")]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(app, ["task", "search", "--workspace-id", "W1"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 1
        mock_client.search_tasks.assert_awaited_once_with("W1", "")

    @patch("clickup.cli.commands.task.get_client")
    def test_search_with_query_passes_through(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [Task(id="t1", name="Match")]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(app, ["task", "search", "--query", "hello", "--workspace-id", "W1"])
        assert result.exit_code == 0
        mock_client.search_tasks.assert_awaited_once_with("W1", "hello")


class TestSearchStatusFilter:
    @patch("clickup.cli.commands.task.get_client")
    def test_status_filters_results(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="Open", status={"status": "to do", "type": "open"}),
            Task(id="t2", name="Done", status={"status": "complete", "type": "closed"}),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--status", "to do"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 1
        assert data["data"][0]["id"] == "t1"

    @patch("clickup.cli.commands.task.get_client")
    def test_multi_status_csv(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="A", status={"status": "to do", "type": "open"}),
            Task(id="t2", name="B", status={"status": "in progress", "type": "custom"}),
            Task(id="t3", name="C", status={"status": "complete", "type": "closed"}),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--status", "to do,in progress"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 2
        assert {t["id"] for t in data["data"]} == {"t1", "t2"}


class TestSearchSort:
    @patch("clickup.cli.commands.task.get_client")
    def test_sort_by_priority(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="Low", priority={"id": "4", "priority": "4"}),
            Task(id="t2", name="Urgent", priority={"id": "1", "priority": "1"}),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--sort", "priority"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert [t["id"] for t in data["data"]] == ["t2", "t1"]

    @patch("clickup.cli.commands.task.get_client")
    def test_sort_desc(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="A", priority={"id": "1", "priority": "1"}),
            Task(id="t2", name="B", priority={"id": "4", "priority": "4"}),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--sort", "priority:desc"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert [t["id"] for t in data["data"]] == ["t2", "t1"]


class TestSearchOpenOnly:
    @patch("clickup.cli.commands.task.get_client")
    def test_open_only_hides_closed(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="Open", status={"status": "to do", "type": "open"}),
            Task(id="t2", name="Closed", status={"status": "complete", "type": "closed"}),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--open-only"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 1
        assert data["data"][0]["id"] == "t1"


class TestSearchUpdatedSince:
    @patch("clickup.cli.commands.task.get_client")
    def test_updated_since_filters(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [
            Task(id="t1", name="Old", date_updated="1000"),
            Task(id="t2", name="New", date_updated="1800000000000"),
        ]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            [
                "task",
                "search",
                "--query",
                "x",
                "--workspace-id",
                "W1",
                "--updated-since",
                "2025-01-01",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 1
        assert data["data"][0]["id"] == "t2"


class TestSearchLimit:
    @patch("clickup.cli.commands.task.get_client")
    def test_limit_caps_results(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [Task(id=f"t{i}", name=f"Task {i}") for i in range(10)]
        mock_get_client.return_value = _ctx(mock_client)

        result = runner.invoke(
            app,
            ["task", "search", "--query", "x", "--workspace-id", "W1", "--limit", "3"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["count"] == 3


class TestSearchNoWorkspaceErrors:
    def test_no_workspace_errors(self):
        result = runner.invoke(app, ["task", "search", "--query", "foo"])
        assert result.exit_code != 0
        assert "workspace" in result.stderr.lower()
