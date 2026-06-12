"""Additional tests to fill remaining coverage gaps.

Targets: config validate / whoami, get_client error paths, bulk error paths,
setup error paths, discover error paths.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.cli.output import set_format
from clickup.core.exceptions import ClickUpError
from clickup.core.models import User

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_format():
    set_format("table")
    yield
    set_format("table")


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


# ---------- config validate / whoami -----------------------------------------


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_valid_token(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (
        True,
        "Authenticated",
        User(id=1, username="evan", email="e@x.com", color="#fff", profilePicture="x"),
    )
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code == 0
            assert "evan" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_invalid_token(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "bad token", None)
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_bogus"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code != 0
            assert "bad token" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_validate_exception(mock_client_cls):
    mock_client_cls.side_effect = Exception("network down")

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "validate"])
            assert result.exit_code != 0
            assert "network down" in result.output


@patch("clickup.cli.commands.config.get_provider")
def test_config_whoami_authenticated(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=1, username="evan", email="e@x.com", color="#fff")
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["config", "whoami"])
            assert result.exit_code == 0
            assert "evan" in result.output


def test_config_whoami_no_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            with patch.dict("os.environ", {}, clear=False):
                # Explicitly clear CLICKUP_*
                from os import environ

                for k in [k for k in environ if k.startswith("CLICKUP_")]:
                    environ.pop(k, None)
                result = runner.invoke(app, ["config", "whoami"])
                assert result.exit_code != 0
                assert "credentials" in result.output.lower()


# ---------- get_client / no-credentials paths --------------------------------


def test_workspace_list_no_credentials():
    """Without a token, workspace list refuses with a setup hint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            from os import environ

            for k in [k for k in environ if k.startswith("CLICKUP_")]:
                environ.pop(k, None)
            result = runner.invoke(app, ["workspace", "list"])
            assert result.exit_code != 0
            assert "API token" in result.output


def test_task_list_no_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            from os import environ

            for k in [k for k in environ if k.startswith("CLICKUP_")]:
                environ.pop(k, None)
            result = runner.invoke(app, ["task", "list", "--list-id", "L1"])
            assert result.exit_code != 0


def test_discover_hierarchy_no_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            from os import environ

            for k in [k for k in environ if k.startswith("CLICKUP_")]:
                environ.pop(k, None)
            result = runner.invoke(app, ["discover", "hierarchy"])
            assert result.exit_code != 0


# ---------- workspace error paths --------------------------------------------


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_list_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.side_effect = ClickUpError("rate limited")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 1
    assert "rate limited" in result.stderr


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_list_unexpected_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.side_effect = RuntimeError("kapow")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 1
    assert "kapow" in result.stderr


# ---------- bulk error paths -------------------------------------------------


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_export_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.side_effect = ClickUpError("nope")
    mock_get_client.return_value = _ctx(mock_client)

    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        result = runner.invoke(
            app,
            ["bulk", "export-tasks", "--list-id", "L1", "--output", f.name],
        )
    assert result.exit_code == 1
    assert "nope" in result.stderr


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_update_no_updates_specified(mock_get_client):
    mock_client = AsyncMock()
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1"])
    assert result.exit_code != 0
    assert "at least one update" in result.stderr.lower()


@patch("clickup.cli.commands.bulk.get_client")
def test_bulk_update_no_matches_warns(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["bulk", "bulk-update", "--list-id", "L1", "--status", "done", "--yes"])
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


# ---------- setup error paths ------------------------------------------------


@patch("clickup.cli.commands.setup.ClickUpClient")
def test_setup_token_validation_fails_in_non_interactive(mock_client_cls):
    """Bad --token in --non-interactive mode errors."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "rejected", None)
    mock_client_cls.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["setup", "run", "--token", "pk_bad", "--non-interactive"])
    assert result.exit_code == 2
    assert "Token rejected" in result.stderr


# ---------- discover error paths ---------------------------------------------


@patch("clickup.cli.commands.discover.get_client")
def test_discover_hierarchy_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.side_effect = ClickUpError("server fault")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "hierarchy"])
    assert result.exit_code == 1
    assert "server fault" in result.stderr


@patch("clickup.cli.commands.discover.get_client")
def test_discover_ids_api_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.side_effect = ClickUpError("server fault")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "ids"])
    assert result.exit_code == 1
