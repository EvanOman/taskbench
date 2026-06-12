"""Tests for top-level CLI commands in clickup/cli/main.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.cli.output import set_format
from clickup.core.models import List as ClickUpList
from clickup.core.models import Space, Team

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_format():
    """The global format state bleeds across test invocations — reset it."""
    set_format("table")
    yield
    set_format("table")


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "version" in data
    assert data["name"] == "ClickUp Toolkit CLI"


def test_status_no_token():
    """Status without a token reports it cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "No API token" in result.output


@patch("clickup.cli.main.get_provider")
def test_status_with_valid_token(mock_client_cls):
    """Status with valid token shows user info."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="evan", email="e@x.com"))
    mock_client.get_teams.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "evan" in result.output


@patch("clickup.cli.main.get_provider")
def test_status_with_full_defaults(mock_client_cls):
    """Status resolves and displays default team / space / list names."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="evan", email="e@x.com"))
    mock_client.get_team.return_value = Team(id="T1", name="Acme", color="#000", members=[])
    mock_client.get_space.return_value = Space(id="S1", name="Eng", private=False, statuses=[], multiple_assignees=True)
    mock_client.get_list.return_value = ClickUpList(id="L1", name="Sprint", task_count=5)
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            runner.invoke(app, ["config", "set", "default_team_id", "T1"])
            runner.invoke(app, ["config", "set", "default_space_id", "S1"])
            runner.invoke(app, ["config", "set", "default_list_id", "L1"])

            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "Acme" in result.output
            assert "Eng" in result.output
            assert "Sprint" in result.output


@patch("clickup.cli.main.get_provider")
def test_status_json(mock_client_cls):
    """Status emits parseable JSON in --format json mode."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_teams.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "json", "status"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "auth_status" in data
            assert "auth_valid" in data


@patch("clickup.cli.main.get_provider")
def test_status_invalid_token(mock_client_cls):
    """Status with an invalid token reports the failure."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "bad token", None)
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_bogus"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "bad token" in result.output


@patch("clickup.cli.main.get_provider")
def test_status_auto_detects_single_workspace(mock_client_cls):
    """Status auto-detects implicit_team if exactly one workspace exists."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_teams.return_value = [Team(id="W1", name="Solo", color="#000", members=[])]
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "Solo" in result.output
            assert "auto-detected" in result.output


@patch("clickup.cli.main.get_provider")
def test_status_partial_defaults(mock_client_cls):
    """Status hints when some defaults are missing."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_team.return_value = Team(id="T1", name="Acme", color="#000", members=[])
    mock_client.get_teams.return_value = []
    mock_client_cls.return_value = _ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            runner.invoke(app, ["config", "set", "default_team_id", "T1"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "setup run" in result.output  # hint to finish setup


def test_help_shows_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Get started" in result.output or "Task workflow" in result.output or "Workspace" in result.output


def test_version_json_shape():
    """version emits {"name": ..., "version": ...} in JSON mode."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "ClickUp Toolkit CLI"
    assert isinstance(data["version"], str)


def test_version_table_mode():
    """version --format table still emits human-readable text."""
    result = runner.invoke(app, ["--format", "table", "version"])
    assert result.exit_code == 0
    assert "ClickUp Toolkit CLI" in result.output


def test_status_json_no_rich_highlighting():
    """status JSON mode should not contain Rich markup/highlighting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["--format", "json", "status"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "provider" in data
            assert "auth_valid" in data
