"""Tests for `clickup setup run --auto` — fully automatic setup."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from clickup.cli.main import app

from .conftest import make_mock_ctx, named_mock

runner = CliRunner()


def _named(**kw):
    return named_mock(**kw)


def _mock_client(*, validate_ok=True, teams=None, spaces=None, lists=None, folders=None):
    """Build an AsyncMock ClickUpClient with sensible defaults."""
    c = AsyncMock()
    c.validate_auth.return_value = (
        validate_ok,
        "ok" if validate_ok else "bad token",
        _named(id=1, username="evan", email="evan@example.com") if validate_ok else None,
    )
    c.get_teams.return_value = teams or []
    c.get_spaces.return_value = spaces or []
    c.get_folders.return_value = folders or []
    c.get_lists.return_value = []
    c.get_folderless_lists.return_value = lists or []
    c.get_list.return_value = (lists or [_named(id="L1", name="X", task_count=0)])[0]
    return c


def _ctx(client):
    return make_mock_ctx(client)


# ---------------------------------------------------------------------------
# Happy path: single workspace/space/list
# ---------------------------------------------------------------------------


class TestAutoSingleOption:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_single_everything_auto_selects(self, mock_cls):
        """Single workspace + space + list: auto picks all, no prompt."""
        team = _named(id="T1", name="Acme")
        space = _named(id="S1", name="Engineering")
        lst = _named(id="L1", name="Sprint", task_count=10)
        client = _mock_client(teams=[team], spaces=[space], lists=[lst])
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["default_team_id"] == "T1"
        assert payload["default_space_id"] == "S1"
        assert payload["default_list_id"] == "L1"
        assert payload["default_list_name"] == "Sprint"


# ---------------------------------------------------------------------------
# Multiple lists: picks max task_count and warns on stderr
# ---------------------------------------------------------------------------


class TestAutoMultipleLists:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_picks_max_task_count_list(self, mock_cls):
        """With multiple lists, auto picks the one with the most tasks."""
        team = _named(id="T1", name="Acme")
        space = _named(id="S1", name="Eng")
        lists = [
            _named(id="L1", name="Few", task_count=2),
            _named(id="L2", name="Many", task_count=20),
            _named(id="L3", name="Some", task_count=5),
        ]
        client = _mock_client(teams=[team], spaces=[space], lists=lists)
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["default_list_id"] == "L2"
        assert payload["default_list_name"] == "Many"

    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_warns_on_stderr_about_auto_selection(self, mock_cls):
        """Auto-selected list emits a warning on stderr."""
        team = _named(id="T1", name="Acme")
        space = _named(id="S1", name="Eng")
        lists = [
            _named(id="L1", name="Few", task_count=2),
            _named(id="L2", name="Many", task_count=20),
        ]
        client = _mock_client(teams=[team], spaces=[space], lists=lists)
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test"],
        )
        assert result.exit_code == 0
        # render_message("warn") goes to stderr in JSON mode
        assert "Auto-selected" in result.stderr or "Auto-selected" in result.output


# ---------------------------------------------------------------------------
# Multiple workspaces without --team-id: exits 2
# ---------------------------------------------------------------------------


class TestAutoMultipleWorkspaces:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_exits_2_listing_options(self, mock_cls):
        teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
        client = _mock_client(teams=teams)
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(app, ["setup", "run", "--auto", "--token", "pk_test"])
        assert result.exit_code == 2
        assert "--team-id" in result.output or "--team-id" in result.stderr


# ---------------------------------------------------------------------------
# Multiple spaces without --space-id: exits 2
# ---------------------------------------------------------------------------


class TestAutoMultipleSpaces:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_exits_2(self, mock_cls):
        team = _named(id="T1", name="Acme")
        spaces = [_named(id="S1", name="Eng"), _named(id="S2", name="Design")]
        client = _mock_client(teams=[team], spaces=spaces)
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(app, ["setup", "run", "--auto", "--token", "pk_test"])
        assert result.exit_code == 2
        assert "--space-id" in result.output or "--space-id" in result.stderr


# ---------------------------------------------------------------------------
# Explicit flags override auto-selection
# ---------------------------------------------------------------------------


class TestAutoExplicitFlags:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_team_id_overrides(self, mock_cls):
        teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
        space = _named(id="S1", name="Eng")
        lst = _named(id="L1", name="Sprint", task_count=5)
        client = _mock_client(teams=teams, spaces=[space], lists=[lst])
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test", "--team-id", "T2"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["default_team_id"] == "T2"

    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_space_id_overrides(self, mock_cls):
        team = _named(id="T1", name="A")
        spaces = [_named(id="S1", name="X"), _named(id="S2", name="Y")]
        lst = _named(id="L1", name="Sprint", task_count=5)
        client = _mock_client(teams=[team], spaces=spaces, lists=[lst])
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test", "--space-id", "S2"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["default_space_id"] == "S2"

    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_list_id_overrides(self, mock_cls):
        team = _named(id="T1", name="A")
        space = _named(id="S1", name="X")
        lists = [
            _named(id="L1", name="Few", task_count=2),
            _named(id="L2", name="Many", task_count=20),
        ]
        client = _mock_client(teams=[team], spaces=[space], lists=lists)
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test", "--list-id", "L1"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        # Explicit --list-id overrides the auto max-tasks pick
        assert payload["default_list_id"] == "L1"


# ---------------------------------------------------------------------------
# No token: exits 2
# ---------------------------------------------------------------------------


class TestAutoNoToken:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_no_token_exits_2(self, mock_cls):
        result = runner.invoke(app, ["setup", "run", "--auto"])
        assert result.exit_code == 2
        assert "token" in result.output.lower() or "token" in result.stderr.lower()


# ---------------------------------------------------------------------------
# No lists: warns but succeeds
# ---------------------------------------------------------------------------


class TestAutoNoLists:
    @patch("clickup.cli.commands.setup.ClickUpClient")
    def test_no_lists_warns_succeeds(self, mock_cls):
        team = _named(id="T1", name="A")
        space = _named(id="S1", name="X")
        client = _mock_client(teams=[team], spaces=[space], lists=[])
        client.get_folders.return_value = []
        mock_cls.return_value = _ctx(client)

        result = runner.invoke(
            app,
            ["--format", "json", "setup", "run", "--auto", "--token", "pk_test"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert "default_list_id" not in payload
        assert payload["default_team_id"] == "T1"
        assert payload["default_space_id"] == "S1"
