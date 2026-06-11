"""Tests for `clickup setup run` — non-interactive flag-driven flows.

The wizard is interactive by default but accepts --token / --team-id /
--space-id / --list-id / --non-interactive for agent use. These tests pin
both behaviors and exercise the auto-selection / mismatch / refusal paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from clickup.cli.main import app

runner = CliRunner()


def _named(**kw):
    """Build a Mock where `.name` is a real string."""
    name = kw.pop("name", None)
    m = Mock(**kw)
    if name is not None:
        m.name = name
    return m


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
