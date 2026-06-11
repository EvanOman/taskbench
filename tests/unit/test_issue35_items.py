"""Tests for GitHub issue #35 items 3, 4, 5, 6, 8.

Covers: hierarchy truncation markers, bulk --all-lists, list aliases,
folderless-only info, brief fields on folder/list, and _brief date_updated.
"""

from __future__ import annotations

import json
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clickup.cli import output
from clickup.cli.output import (
    _BRIEF_TASK_FIELDS,
    FormatChoice,
    render_folder,
    render_hierarchy,
    render_list,
    set_format,
)
from clickup.core.models import (
    Assignee,
    Folder,
    PriorityInfo,
    Space,
    StatusInfo,
    Task,
    Team,
    User,
)
from clickup.core.models import List as ClickUpList

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_format():
    set_format(FormatChoice.table)
    yield
    set_format(FormatChoice.table)


@pytest.fixture
def capture_console(monkeypatch):
    from rich.console import Console as RConsole

    buf = StringIO()
    monkeypatch.setattr(output, "_console", RConsole(file=buf, force_terminal=False, width=200))
    return buf


def _user(**kw: Any) -> User:
    base: dict[str, Any] = {"id": 1, "username": "evan", "email": "evan@example.com", "color": "#fff"}
    base.update(kw)
    return User(**base)


def _list(**kw: Any) -> ClickUpList:
    base: dict[str, Any] = {"id": "L1", "name": "Sprint 42", "task_count": 7}
    base.update(kw)
    return ClickUpList(**base)


def _folder(**kw: Any) -> Folder:
    from clickup.core.models import SpaceRef

    base: dict[str, Any] = {
        "id": "F1",
        "name": "Backend",
        "orderindex": 0,
        "override_statuses": False,
        "hidden": False,
        "space": SpaceRef(id="S1", name="Eng"),
        "task_count": "12",
    }
    base.update(kw)
    return Folder(**base)


def _task(**kw: Any) -> Task:
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


def _team(**kw: Any) -> Team:
    base: dict[str, Any] = {"id": "T1", "name": "Acme", "color": "#000", "members": []}
    base.update(kw)
    return Team(**base)


def _space(**kw: Any) -> Space:
    base: dict[str, Any] = {
        "id": "S1",
        "name": "Engineering",
        "private": False,
        "statuses": [],
        "multiple_assignees": True,
    }
    base.update(kw)
    return Space(**base)


# ---------------------------------------------------------------------------
# Item 3 — discover hierarchy truncation marker
# ---------------------------------------------------------------------------


class TestHierarchyTruncation:
    """Truncated nodes carry ``truncated_at_depth`` in JSON; table mode gets a stderr warning."""

    def test_truncation_marker_depth_1_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """depth=1 truncates workspaces — spaces are empty, marker present."""

        # Build hierarchy data at depth 1 to verify the marker directly
        set_format("json")
        data = {"workspaces": [{"id": "T1", "name": "Acme", "spaces": [], "truncated_at_depth": True}]}
        render_hierarchy(data)
        result = json.loads(capsys.readouterr().out)
        assert result["workspaces"][0]["truncated_at_depth"] is True

    def test_truncation_marker_depth_3_folders(self, capsys: pytest.CaptureFixture[str]) -> None:
        """depth=3 truncates folders — lists are empty, marker present on folders."""
        set_format("json")
        data = {
            "workspaces": [
                {
                    "id": "T1",
                    "name": "Acme",
                    "spaces": [
                        {
                            "id": "S1",
                            "name": "Eng",
                            "folders": [{"id": "F1", "name": "Backend", "lists": [], "truncated_at_depth": True}],
                            "folderless_lists": [],
                        }
                    ],
                }
            ]
        }
        render_hierarchy(data)
        result = json.loads(capsys.readouterr().out)
        assert result["workspaces"][0]["spaces"][0]["folders"][0]["truncated_at_depth"] is True

    def test_truncation_marker_depth_2_spaces(self, capsys: pytest.CaptureFixture[str]) -> None:
        """depth=2 truncates spaces — folders/lists are empty, marker present on spaces."""
        set_format("json")
        data = {
            "workspaces": [
                {
                    "id": "T1",
                    "name": "Acme",
                    "spaces": [
                        {
                            "id": "S1",
                            "name": "Eng",
                            "folders": [],
                            "folderless_lists": [],
                            "truncated_at_depth": True,
                        }
                    ],
                }
            ]
        }
        render_hierarchy(data)
        result = json.loads(capsys.readouterr().out)
        assert result["workspaces"][0]["spaces"][0]["truncated_at_depth"] is True

    def test_no_marker_when_full_depth(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Full-depth hierarchy has no truncation markers."""
        set_format("json")
        data = {
            "workspaces": [
                {
                    "id": "T1",
                    "name": "Acme",
                    "spaces": [
                        {
                            "id": "S1",
                            "name": "Eng",
                            "folders": [
                                {
                                    "id": "F1",
                                    "name": "Backend",
                                    "lists": [{"id": "L1", "name": "Sprint", "task_count": 5}],
                                }
                            ],
                            "folderless_lists": [],
                        }
                    ],
                }
            ]
        }
        render_hierarchy(data)
        raw = capsys.readouterr().out
        assert "truncated_at_depth" not in raw

    def test_table_mode_truncation_warning(self, capture_console: StringIO, capsys: pytest.CaptureFixture[str]) -> None:
        """In table mode, truncated hierarchy triggers a stderr warning."""
        from clickup.cli.commands.discover import show_hierarchy

        # Simulate a truncated hierarchy via the discover command at depth=1
        mock_team = _team()

        async def fake_get_team(tid: str) -> Team:
            return mock_team

        async def fake_get_teams() -> list[Team]:
            return [mock_team]

        mock_client = AsyncMock()
        mock_client.get_teams = fake_get_teams
        mock_client.get_team = fake_get_team
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("clickup.cli.commands.discover.get_client", return_value=mock_client):
            # depth=1 means spaces are truncated
            show_hierarchy(workspace_id=None, team_id=None, max_depth=1)

        stderr = capsys.readouterr().err
        assert "truncated" in stderr.lower() or "depth" in stderr.lower()


# ---------------------------------------------------------------------------
# Item 4 — bulk bulk-update --all-lists
# ---------------------------------------------------------------------------


def _mock_config_with_lists(
    aliases: dict[str, str] | None,
) -> MagicMock:
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

    def test_all_lists_dry_run(self, tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
        """--all-lists --dry-run previews tasks across multiple lists."""
        from clickup.cli.commands.bulk import bulk_update

        tasks_a = [_task(id="t1", name="Task A")]
        tasks_b = [_task(id="t2", name="Task B")]
        client = self._make_mock_client({"list_a": tasks_a, "list_b": tasks_b})

        with (
            patch("clickup.cli.commands.bulk.get_client", return_value=client),
            patch("clickup.cli.commands.bulk.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
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

    def test_all_lists_force_updates(self, tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
        """--all-lists --force actually applies updates across lists."""
        from clickup.cli.commands.bulk import bulk_update

        tasks_a = [_task(id="t1", name="Task A")]
        tasks_b = [_task(id="t2", name="Task B")]
        client = self._make_mock_client({"list_a": tasks_a, "list_b": tasks_b})

        with (
            patch("clickup.cli.commands.bulk.get_client", return_value=client),
            patch("clickup.cli.commands.bulk.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
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

    def test_all_lists_refuses_without_force(self, tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
        """Without --force, exits 2."""
        import typer as _typer

        from clickup.cli.commands.bulk import bulk_update

        tasks_a = [_task(id="t1", name="Task A")]
        client = self._make_mock_client({"list_a": tasks_a})

        with (
            patch("clickup.cli.commands.bulk.get_client", return_value=client),
            patch("clickup.cli.commands.bulk.Config", return_value=_mock_config_with_lists({"inbox": "list_a"})),
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

    def test_all_lists_no_aliases_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--all-lists with no configured aliases is a usage error (exit 2)."""
        import typer as _typer

        from clickup.cli.commands.bulk import bulk_update

        with (
            patch("clickup.cli.commands.bulk.Config", return_value=_mock_config_with_lists(None)),
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

    def test_all_lists_continues_through_per_list_failure(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Per-list fetch failure doesn't abort remaining lists."""
        from clickup.cli.commands.bulk import bulk_update
        from clickup.core.exceptions import ClickUpError

        tasks_b = [_task(id="t2", name="Task B")]
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
            patch("clickup.cli.commands.bulk.get_client", return_value=client),
            patch("clickup.cli.commands.bulk.Config", return_value=_mock_config_with_lists(self._TWO_LISTS)),
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


# ---------------------------------------------------------------------------
# Item 5 — list noun/verb aliases
# ---------------------------------------------------------------------------


class TestListAliases:
    """``list list`` and ``list ls`` should be registered commands."""

    def test_list_list_alias_registered(self) -> None:
        from clickup.cli.commands.list import app

        command_names = [cmd.name for cmd in app.registered_commands]
        assert "list" in command_names

    def test_list_ls_alias_registered(self) -> None:
        from clickup.cli.commands.list import app

        command_names = [cmd.name for cmd in app.registered_commands]
        assert "ls" in command_names

    def test_show_still_registered(self) -> None:
        from clickup.cli.commands.list import app

        command_names = [cmd.name for cmd in app.registered_commands]
        assert "show" in command_names


# ---------------------------------------------------------------------------
# Item 6 — list show --space-id folderless-only info
# ---------------------------------------------------------------------------


class TestListShowSpaceIdInfo:
    """--space-id emits an info message about folderless-only semantics."""

    def test_space_id_info_message_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """In JSON mode info-level messages are suppressed (render_message contract)."""
        from clickup.cli.commands.list import list_lists

        set_format("json")

        mock_client = AsyncMock()
        mock_client.get_folderless_lists = AsyncMock(return_value=[_list()])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("clickup.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id=None, space_id="S1")

        captured = capsys.readouterr()
        # JSON mode suppresses info-level messages entirely; the hint is
        # table-mode-only (see render_message). stderr must stay clean.
        assert captured.err == ""

    def test_space_id_info_message_table(
        self,
        capture_console: StringIO,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """In table mode the info message mentions 'discover hierarchy'."""
        from clickup.cli.commands.list import list_lists

        mock_client = AsyncMock()
        mock_client.get_folderless_lists = AsyncMock(return_value=[_list()])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("clickup.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id=None, space_id="S1")

        # Info in table mode goes to stdout via rich console
        console_out = capture_console.getvalue()
        assert "folderless" in console_out.lower() or "discover hierarchy" in console_out.lower()

    def test_folder_id_no_info_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--folder-id does NOT emit the folderless info."""
        from clickup.cli.commands.list import list_lists

        set_format("json")

        mock_client = AsyncMock()
        mock_client.get_lists = AsyncMock(return_value=[_list()])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("clickup.cli.commands.list.get_client", return_value=mock_client):
            list_lists(folder_id="F1", space_id=None)

        captured = capsys.readouterr()
        assert "folderless" not in captured.err.lower()


# ---------------------------------------------------------------------------
# Item 8 — _brief projection includes date_updated
# ---------------------------------------------------------------------------


class TestBriefDateUpdated:
    """date_updated is now in the brief field set."""

    def test_date_updated_in_brief_fields(self) -> None:
        assert "date_updated" in _BRIEF_TASK_FIELDS

    def test_brief_json_includes_date_updated(self, capsys: pytest.CaptureFixture[str]) -> None:
        set_format("json")
        from clickup.cli.output import render_task

        render_task(_task(), brief=True)
        data = json.loads(capsys.readouterr().out)
        assert "date_updated" in data
        assert data["date_updated"].endswith("Z")


# ---------------------------------------------------------------------------
# Item 8 — --brief on folder get and list get
# ---------------------------------------------------------------------------


class TestFolderBrief:
    """render_folder(brief=True) strips to identity fields only."""

    def test_brief_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        set_format("json")
        render_folder(_folder(), brief=True)
        data = json.loads(capsys.readouterr().out)
        assert "id" in data
        assert "name" in data
        assert "task_count" in data
        # Full fields like orderindex should be absent
        assert "orderindex" not in data
        assert "override_statuses" not in data

    def test_full_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        set_format("json")
        render_folder(_folder())
        data = json.loads(capsys.readouterr().out)
        assert "orderindex" in data


class TestListBrief:
    """render_list(brief=True) strips to identity fields only."""

    def test_brief_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        set_format("json")
        render_list(_list(), brief=True)
        data = json.loads(capsys.readouterr().out)
        assert "id" in data
        assert "name" in data
        assert "task_count" in data
        # Full fields like archived should be absent
        assert "archived" not in data
        assert "due_date" not in data

    def test_brief_table_no_content(self, capture_console: StringIO) -> None:
        render_list(_list(content="Secret details"), brief=True)
        out = capture_console.getvalue()
        assert "Secret details" not in out

    def test_full_table_has_content(self, capture_console: StringIO) -> None:
        render_list(_list(content="Secret details"), brief=False)
        out = capture_console.getvalue()
        assert "Secret details" in out
