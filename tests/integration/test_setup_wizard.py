"""Tests for `clickup setup run` — non-interactive and interactive flows.

Consolidates tests from the original test_setup_wizard.py, plus setup tests
formerly in test_final_coverage.py and test_more_coverage.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app

from .conftest import make_mock_ctx, named_mock

runner = CliRunner()


def _named(**kw):
    """Build a Mock where `.name` is a real string."""
    return named_mock(**kw)


def _mock_client(*, validate_ok=True, teams=None, spaces=None, lists=None, folders=None, tasks=None):
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
    c.get_tasks.return_value = tasks or []
    return c


def _ctx(client):
    """Wrap an AsyncMock client in an async-context-manager Mock."""
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


# ---------- token handling ----------------------------------------------------


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_non_interactive_no_token_refuses(mock_client_cls):
    """--non-interactive without a token (and no env) errors out."""
    result = runner.invoke(app, ["setup", "run", "--non-interactive"])
    assert result.exit_code == 2
    assert "No API token configured" in result.stderr


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_with_token_and_single_workspace_auto_selects(mock_client_cls):
    """All flags + single team/space/list = no prompts, success."""
    team = _named(id="T1", name="Acme")
    space = _named(id="S1", name="Eng")
    lst = _named(id="L1", name="Sprint", task_count=5)
    client = _mock_client(teams=[team], spaces=[space], lists=[lst])
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(app, ["--format", "table", "setup", "run", "--token", "pk_test", "--non-interactive"])
    assert result.exit_code == 0, result.output
    assert "Auto-selected workspace" in result.output
    assert "Auto-selected space" in result.output


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_with_all_flags_no_prompts(mock_client_cls):
    """All ID flags supplied -> exact selection, no prompts."""
    teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
    spaces = [_named(id="S1", name="X"), _named(id="S2", name="Y")]
    lists = [_named(id="L1", name="Sprint", task_count=5)]
    client = _mock_client(teams=teams, spaces=spaces, lists=lists)

    # First get_spaces returns spaces of chosen team — same mock returns regardless
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(
        app,
        [
            "--format",
            "table",
            "setup",
            "run",
            "--token",
            "pk_test",
            "--team-id",
            "T2",
            "--space-id",
            "S2",
            "--list-id",
            "L1",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "via --team-id" in result.output
    assert "via --space-id" in result.output
    assert "via --list-id" in result.output


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_invalid_team_id_errors(mock_client_cls):
    """--team-id that doesn't match any team exits 2."""
    teams = [_named(id="T1", name="Real")]
    client = _mock_client(teams=teams)
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(
        app,
        ["setup", "run", "--token", "pk_test", "--team-id", "T999", "--non-interactive"],
    )
    assert result.exit_code == 2
    assert "not found" in result.stderr


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_invalid_space_id_errors(mock_client_cls):
    """--space-id that doesn't match any space exits 2."""
    team = _named(id="T1", name="Acme")
    spaces = [_named(id="S1", name="Real")]
    client = _mock_client(teams=[team], spaces=spaces)
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(
        app,
        ["setup", "run", "--token", "pk_test", "--space-id", "S999", "--non-interactive"],
    )
    assert result.exit_code == 2
    assert "not found" in result.stderr


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_invalid_list_id_errors(mock_client_cls):
    """--list-id that doesn't match exits 2."""
    team = _named(id="T1", name="Acme")
    space = _named(id="S1", name="Eng")
    lst = _named(id="L1", name="Real", task_count=5)
    client = _mock_client(teams=[team], spaces=[space], lists=[lst])
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(
        app,
        ["setup", "run", "--token", "pk_test", "--list-id", "L999", "--non-interactive"],
    )
    assert result.exit_code == 2
    assert "not found" in result.stderr


# ---------- ambiguous selection without flags --------------------------------


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_non_interactive_multiple_teams_refuses(mock_client_cls):
    """Two teams + --non-interactive without --team-id errors with hint."""
    teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
    client = _mock_client(teams=teams)
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_test", "--non-interactive"])
    assert result.exit_code == 2
    assert "--team-id" in result.stderr


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_non_interactive_multiple_spaces_refuses(mock_client_cls):
    """Multiple spaces + --non-interactive without --space-id errors."""
    team = _named(id="T1", name="A")
    spaces = [_named(id="S1", name="X"), _named(id="S2", name="Y")]
    client = _mock_client(teams=[team], spaces=spaces)
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(
        app,
        ["setup", "run", "--token", "pk_test", "--team-id", "T1", "--non-interactive"],
    )
    assert result.exit_code == 2
    assert "--space-id" in result.stderr


# ---------- empty workspaces / spaces ----------------------------------------


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_no_workspaces_errors(mock_client_cls):
    """No workspaces in account exits 1."""
    client = _mock_client(teams=[])
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_test", "--non-interactive"])
    assert result.exit_code == 1
    assert "No workspaces" in result.output


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_no_spaces_errors(mock_client_cls):
    """No spaces in workspace exits 1."""
    team = _named(id="T1", name="A")
    client = _mock_client(teams=[team], spaces=[])
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_test", "--non-interactive"])
    assert result.exit_code == 1
    assert "No spaces" in result.output


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_no_lists_warns_but_succeeds(mock_client_cls):
    """No lists in space is a warning, not a hard error."""
    team = _named(id="T1", name="A")
    space = _named(id="S1", name="X")
    client = _mock_client(teams=[team], spaces=[space], lists=[])
    client.get_folders.return_value = []
    mock_client_cls.return_value = _ctx(client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_test", "--non-interactive"])
    assert result.exit_code == 0
    assert "No lists found" in result.output


# =============================================================================
# interactive paths — from test_final_coverage.py
# =============================================================================


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_token_prompt(mock_client_cls, mock_prompt):
    """User enters a valid token at the prompt."""
    mock_prompt.return_value = "pk_entered"
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = []
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["setup", "run"])
            assert result.exit_code == 0
            assert mock_prompt.called


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_pick_workspace_menu(mock_client_cls, mock_prompt):
    """Two workspaces -> _pick_from_menu prompts for selection."""
    mock_prompt.return_value = "1"
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    teams = [_named(id="T1", name="A"), _named(id="T2", name="B")]
    spaces = [_named(id="S1", name="X")]
    mock_client.get_teams.return_value = teams
    mock_client.get_spaces.return_value = spaces
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = []
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0
    assert "A" in result.output


@patch("clickup.cli.commands.setup.typer.confirm")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_list_use_suggested(mock_client_cls, mock_confirm):
    """confirm=Yes accepts the suggested list."""
    mock_confirm.return_value = True
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [
        _named(id="L1", name="High", task_count=10),
        _named(id="L2", name="Low", task_count=2),
    ]
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0
    assert "High" in result.output


@patch("clickup.cli.commands.setup.typer.prompt")
@patch("clickup.cli.commands.setup.typer.confirm")
@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_interactive_list_pick_alternative(mock_client_cls, mock_confirm, mock_prompt):
    """confirm=No, then user enters a list number."""
    mock_confirm.return_value = False
    mock_prompt.return_value = "2"
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [
        _named(id="L1", name="High", task_count=10),
        _named(id="L2", name="Low", task_count=2),
    ]
    mock_client.get_tasks.return_value = []
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk"])
    assert result.exit_code == 0


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_token_validation_then_smoke_test(mock_client_cls):
    """End-to-end happy path: token works, defaults set, smoke test fetches tasks."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", _named(id=1, username="u", email="u@x.com"))
    mock_client.get_teams.return_value = [_named(id="T1", name="A")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="X")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = [_named(id="L1", name="Sprint", task_count=5)]
    mock_client.get_tasks.return_value = [
        Mock(name="task one", status=Mock(status="open")),
        Mock(name="task two", status=Mock(status="open")),
    ]
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "setup", "run", "--token", "pk", "--list-id", "L1", "--non-interactive"],
    )
    assert result.exit_code == 0
    assert "smoke test" in result.output.lower()


# =============================================================================
# setup error paths — from test_more_coverage.py
# =============================================================================


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_token_validation_fails_in_non_interactive(mock_client_cls):
    """Bad --token in --non-interactive mode errors."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "rejected", None)
    mock_client_cls.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_bad", "--non-interactive"])
    assert result.exit_code == 2
    assert "Token rejected" in result.stderr
