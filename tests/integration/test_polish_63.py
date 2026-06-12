"""Tests for issue #63 micro-polish batch (eval run r8).

Covers --ids-only output mode, truncated envelope flag, and help-text assertions.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.models import Task

from .conftest import make_mock_ctx

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(task_id: str, name: str = "T") -> Task:
    return Task(id=task_id, name=name, url=f"https://x/{task_id}")


def _mock_create_client(mock_client: AsyncMock):
    """Wire a mock client through get_client → async-context-manager."""
    return make_mock_ctx(mock_client)


# ==========================================================================
# Item 1 — --ids-only output mode
# ==========================================================================


class TestIdsOnlyCreate:
    @patch("clickup.cli.commands.task.get_client")
    def test_single_create(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = _make_task("abc123", "New")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "create", "New", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "abc123"

    @patch("clickup.cli.commands.task.get_client")
    def test_batch_create(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.create_task.side_effect = [
            _make_task("id1", "A"),
            _make_task("id2", "B"),
        ]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "create", "A", "B", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert lines == ["id1", "id2"]

    @patch("clickup.cli.commands.task.get_client")
    def test_ids_only_json_mode(self, mock_get_client: AsyncMock) -> None:
        """--ids-only prints plain IDs regardless of --format json."""
        mock_client = AsyncMock()
        mock_client.create_task.return_value = _make_task("j1", "J")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["--format", "json", "task", "create", "J", "--list-id", "L1", "--ids-only"])
        assert result.exit_code == 0
        # Must NOT be JSON — just the raw ID
        assert result.stdout.strip() == "j1"

    def test_ids_only_and_brief_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "create", "X", "--list-id", "L1", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyDone:
    @patch("clickup.cli.commands.task.get_client")
    def test_single_done(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task("d1", "Done")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "done", "d1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "d1"

    @patch("clickup.cli.commands.task.get_client")
    def test_batch_done(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.side_effect = [
            _make_task("d1"),
            _make_task("d2"),
        ]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "done", "d1", "d2", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip().splitlines() == ["d1", "d2"]

    def test_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "done", "d1", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyClose:
    @patch("clickup.cli.commands.task.get_client")
    def test_close_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task("c1")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "close", "c1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "c1"


class TestIdsOnlyStart:
    @patch("clickup.cli.commands.task.get_client")
    def test_start_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task("s1")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "start", "s1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "s1"


class TestIdsOnlyPark:
    @patch("clickup.cli.commands.task.get_client")
    def test_park_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task("p1")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "park", "p1", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "p1"


class TestIdsOnlyStatus:
    @patch("clickup.cli.commands.task.get_client")
    def test_status_ids_only(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.update_task.return_value = _make_task("st1")
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "status", "st1", "complete", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "st1"

    def test_mutual_exclusion(self) -> None:
        result = runner.invoke(app, ["task", "status", "st1", "complete", "--ids-only", "--brief"])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr


class TestIdsOnlyDelete:
    @patch("clickup.cli.commands.task.get_client")
    def test_single_delete(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.delete_task.return_value = True
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "delete", "del1", "--force", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "del1"

    @patch("clickup.cli.commands.task.get_client")
    def test_batch_delete(self, mock_get_client: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client.delete_task.return_value = True
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "delete", "del1", "del2", "--force", "--ids-only"])
        assert result.exit_code == 0
        assert result.stdout.strip().splitlines() == ["del1", "del2"]


# ==========================================================================
# Item 6 — truncated envelope flag
# ==========================================================================


class TestTruncatedFlag:
    @patch("clickup.cli.commands.task.get_client")
    def test_truncated_true_when_clipped(self, mock_get_client: AsyncMock) -> None:
        """When result count > limit, envelope has truncated: true."""
        mock_client = AsyncMock()
        # Return 5 tasks but ask for --limit 3
        mock_client.get_tasks.return_value = [_make_task(f"t{i}") for i in range(5)]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "list", "--list-id", "L1", "--limit", "3"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 3

    @patch("clickup.cli.commands.task.get_client")
    def test_no_truncated_when_not_clipped(self, mock_get_client: AsyncMock) -> None:
        """When result count <= limit, truncated key is absent."""
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [_make_task(f"t{i}") for i in range(3)]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "list", "--list-id", "L1", "--limit", "50"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "truncated" not in data
        assert data["count"] == 3

    @patch("clickup.cli.commands.task.get_client")
    def test_truncated_on_search(self, mock_get_client: AsyncMock) -> None:
        """task search also emits truncated when clipped."""
        mock_client = AsyncMock()
        mock_client.search_tasks.return_value = [_make_task(f"t{i}") for i in range(10)]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "search", "--workspace-id", "W1", "--limit", "5"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 5

    @patch("clickup.cli.commands.task.get_client")
    def test_truncated_on_mine(self, mock_get_client: AsyncMock) -> None:
        """task mine also emits truncated when clipped."""
        from clickup.core.models import User

        mock_client = AsyncMock()
        mock_client.get_user.return_value = User(id=42, username="e", email="e@x.com")
        mock_client.search_tasks.return_value = [_make_task(f"t{i}") for i in range(5)]
        mock_get_client.return_value = _mock_create_client(mock_client)

        result = runner.invoke(app, ["task", "mine", "--workspace-id", "W1", "--limit", "3"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["truncated"] is True
        assert data["count"] == 3


# ==========================================================================
# Items 3, 4, 5, 7 — Help text assertions
# ==========================================================================


class TestHelpText:
    def test_list_stats_help_mentions_space_id(self) -> None:
        """Item 3: list stats help mentions --space-id to narrow."""
        result = runner.invoke(app, ["list", "stats", "--help"])
        assert result.exit_code == 0
        assert "use --space-id to narrow" in result.stdout

    def test_brief_help_is_compact(self) -> None:
        """Item 4: --brief help lists actual fields."""
        result = runner.invoke(app, ["task", "list", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout
        assert "date_updated" in result.stdout

    def test_brief_help_on_get(self) -> None:
        result = runner.invoke(app, ["task", "get", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_mine(self) -> None:
        result = runner.invoke(app, ["task", "mine", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_search(self) -> None:
        result = runner.invoke(app, ["task", "search", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_create(self) -> None:
        result = runner.invoke(app, ["task", "create", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_update(self) -> None:
        result = runner.invoke(app, ["task", "update", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_done(self) -> None:
        result = runner.invoke(app, ["task", "done", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_brief_help_on_status(self) -> None:
        result = runner.invoke(app, ["task", "status", "--help"])
        assert result.exit_code == 0
        assert "Compact projection" in result.stdout

    def test_bulk_export_help_mentions_default_list(self) -> None:
        """Item 5: bulk export-tasks help mentions the default-list fallback."""
        result = runner.invoke(app, ["bulk", "export-tasks", "--help"])
        assert result.exit_code == 0
        assert "Defaults to the configured default list" in result.stdout

    def test_task_group_help_mentions_comments(self) -> None:
        """Item 7: task group help mentions the comments subgroup."""
        result = runner.invoke(app, ["task", "--help"])
        assert result.exit_code == 0
        assert "comments" in result.stdout.lower()
        # Verify it specifically mentions the subgroup path
        assert "clickup task comments" in result.stdout


# ==========================================================================
# Item 8 — spec drift fix (Comment.user optional) — verified by model test
# ==========================================================================


class TestCommentUserOptional:
    def test_comment_without_user_is_valid(self) -> None:
        """Comment model accepts user=None (create-response case)."""
        from clickup.core.models import Comment

        comment = Comment(id="c1", comment_text="hi", date="123")
        assert comment.user is None

    def test_comment_with_user_is_valid(self) -> None:
        """Comment model accepts user when present (read case)."""
        from clickup.core.models import Comment, User

        comment = Comment(
            id="c1",
            comment_text="hi",
            date="123",
            user=User(id=1, username="u", email="u@x.com"),
        )
        assert comment.user is not None
        assert comment.user.username == "u"
