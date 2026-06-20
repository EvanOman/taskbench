"""Tests for top-level CLI entry points in taskbench/cli/main.py.

Consolidates tests from test_main_coverage.py and tests/unit/test_main_error_envelope.py.
Covers: status, version, format callback, and the Typer/Click error JSON envelope.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import click
import pytest
from typer.testing import CliRunner

from taskbench.cli.main import _emit_click_error_envelope, _format_hint, _wants_json_mode, app, main
from taskbench.core.models import List as ClickUpList
from taskbench.core.models import Space, Team

runner = CliRunner()


# =============================================================================
# status / version (from test_main_coverage.py)
# =============================================================================


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "version" in data
    assert data["name"] == "Taskbench"


def test_status_no_token():
    """Status without a token reports it cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "No API token" in result.output


@patch("taskbench.cli.main.get_provider")
def test_status_with_valid_token(mock_client_cls):
    """Status with valid token shows user info."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="evan", email="e@x.com"))
    mock_client.get_teams.return_value = []
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "evan" in result.output


@patch("taskbench.cli.main.get_provider")
def test_status_with_full_defaults(mock_client_cls):
    """Status resolves and displays default team / space / list names."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="evan", email="e@x.com"))
    mock_client.get_team.return_value = Team(id="T1", name="Acme", color="#000", members=[])
    mock_client.get_space.return_value = Space(id="S1", name="Eng", private=False, statuses=[], multiple_assignees=True)
    mock_client.get_list.return_value = ClickUpList(id="L1", name="Sprint", task_count=5)
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            runner.invoke(app, ["config", "set", "default_team_id", "T1"])
            runner.invoke(app, ["config", "set", "default_space_id", "S1"])
            runner.invoke(app, ["config", "set", "default_list_id", "L1"])

            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "Acme" in result.output
            assert "Eng" in result.output
            assert "Sprint" in result.output


@patch("taskbench.cli.main.get_provider")
def test_status_json(mock_client_cls):
    """Status emits parseable JSON in --format json mode."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_teams.return_value = []
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "json", "status"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "auth_status" in data
            assert "auth_valid" in data


@patch("taskbench.cli.main.get_provider")
def test_status_invalid_token(mock_client_cls):
    """Status with an invalid token reports the failure."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (False, "bad token", None)
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_bogus"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "bad token" in result.output


@patch("taskbench.cli.main.get_provider")
def test_status_auto_detects_single_workspace(mock_client_cls):
    """Status auto-detects implicit_team if exactly one workspace exists."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_teams.return_value = [Team(id="W1", name="Solo", color="#000", members=[])]
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "Solo" in result.output
            assert "auto-detected" in result.output


@patch("taskbench.cli.main.get_provider")
def test_status_partial_defaults(mock_client_cls):
    """Status hints when some defaults are missing."""
    mock_client = AsyncMock()
    mock_client.validate_auth.return_value = (True, "ok", Mock(username="e", email="e@x.com"))
    mock_client.get_team.return_value = Team(id="T1", name="Acme", color="#000", members=[])
    mock_client.get_teams.return_value = []
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_client
    mock_client_cls.return_value = cm

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            runner.invoke(app, ["config", "set-token", "pk_test"])
            runner.invoke(app, ["config", "set", "default_team_id", "T1"])
            result = runner.invoke(app, ["--format", "table", "status"])
            assert result.exit_code == 0
            assert "setup run" in result.output


def test_help_shows_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Get started" in result.output or "Task workflow" in result.output or "Workspace" in result.output


def test_version_json_shape():
    """version emits {"name": ..., "version": ...} in JSON mode."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "Taskbench"
    assert isinstance(data["version"], str)


def test_version_table_mode():
    """version --format table still emits human-readable text."""
    result = runner.invoke(app, ["--format", "table", "version"])
    assert result.exit_code == 0
    assert "Taskbench" in result.output


def test_status_json_no_rich_highlighting():
    """status JSON mode should not contain Rich markup/highlighting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["--format", "json", "status"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "provider" in data
            assert "auth_valid" in data


def test_cli_format_flag_global():
    """--format json is accepted at the root level."""
    result = runner.invoke(app, ["--format", "json", "template", "list"])
    assert result.exit_code == 0


def test_invalid_subcommand_errors():
    result = runner.invoke(app, ["nonexistent_subcommand"])
    assert result.exit_code == 2


# =============================================================================
# error envelope (from test_main_error_envelope.py)
# =============================================================================


@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], True),  # JSON is the default
        (["task", "list"], True),
        (["--format", "json", "task", "list"], True),
        (["--format=json", "task", "list"], True),
        (["--format", "JSON", "task", "list"], True),
        (["--format", "table", "task", "list"], False),
        (["--format=table", "task", "list"], False),
        (["--format", "csv", "task", "list"], False),
        (["task", "list", "--format", "json"], True),
    ],
)
def test_wants_json_mode_parses_argv(argv: list[str], expected: bool) -> None:
    assert _wants_json_mode(argv) is expected


def test_emit_click_error_envelope_shape(capsys: pytest.CaptureFixture[str]) -> None:
    """The envelope carries error, type, and (when available) command path."""
    exc = click.exceptions.UsageError("No such command 'frobnicate'.")
    _emit_click_error_envelope(exc)
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {"error": "No such command 'frobnicate'.", "type": "UsageError"}


def test_emit_click_error_envelope_with_context(capsys: pytest.CaptureFixture[str]) -> None:
    cmd = click.Command(name="list")
    parent = click.Context(click.Command(name="taskbench"), info_name="taskbench")
    ctx = click.Context(cmd, info_name="list", parent=parent)
    exc = click.exceptions.BadParameter("not a valid integer", ctx=ctx, param_hint="'--limit'")
    _emit_click_error_envelope(exc)
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error"].startswith("Invalid value for '--limit'")
    assert payload["type"] == "BadParameter"
    assert payload["command"] == "taskbench list"


def test_main_emits_json_envelope_for_unknown_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: `taskbench frobnicate` should exit 2 with a JSON error on stderr."""
    monkeypatch.setattr("sys.argv", ["taskbench", "frobnicate"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["type"] == "UsageError"
    assert "frobnicate" in payload["error"]


def test_main_emits_json_envelope_for_bad_type_coercion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`taskbench task list --list-id L --limit abc` -> JSON envelope, exit 2."""
    monkeypatch.setattr("sys.argv", ["taskbench", "task", "list", "--list-id", "L", "--limit", "abc"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["type"] == "BadParameter"
    assert "--limit" in payload["error"]


def test_main_falls_back_to_rich_prose_for_table_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--format table` opts out of the JSON envelope; humans get the usual Click output."""
    monkeypatch.setattr("sys.argv", ["taskbench", "--format", "table", "frobnicate"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "frobnicate" in captured.err
    assert not captured.err.lstrip().startswith("{")


@pytest.fixture
def json_provider_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point the CLI at a seeded JSON store so main() can run end-to-end."""
    from taskbench.core.json_provider import write_seed_store

    store = tmp_path / "store.json"
    write_seed_store(store)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"provider": "json", "json_store_path": str(store), "default_list_id": "list_inbox"}))
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(config))
    return config


def test_main_propagates_app_level_error_exit_code(
    json_provider_env,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["taskbench", "task", "get", "mock_9999"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["type"] == "NotFoundError"


def test_main_propagates_usage_error_exit_code(
    json_provider_env,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["taskbench", "task", "update", "mock_1001", "--priority", "99"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "--priority must be" in json.loads(captured.err)["error"]


def test_main_success_path_exits_zero(
    json_provider_env,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["taskbench", "task", "list", "--brief"])
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["count"] >= 1


def test_main_json_mode_suppresses_info_on_stderr(
    json_provider_env,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["taskbench", "task", "list", "--brief"])
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["count"] >= 1
    assert captured.err == ""


# =============================================================================
# --format hint when placed after subcommand (item 1)
# =============================================================================


class TestFormatHint:
    def test_format_hint_detects_format_option(self) -> None:
        exc = click.exceptions.NoSuchOption("--format")
        assert _format_hint(exc) is not None
        assert "--format" in _format_hint(exc)
        assert "before the subcommand" in _format_hint(exc)

    def test_format_hint_ignores_other_options(self) -> None:
        exc = click.exceptions.NoSuchOption("--foo")
        assert _format_hint(exc) is None

    def test_format_hint_ignores_non_nosuchoption(self) -> None:
        exc = click.exceptions.UsageError("some error")
        assert _format_hint(exc) is None


def test_main_format_after_subcommand_now_works(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``taskbench version --format json`` (trailing global flag) is hoisted and succeeds."""
    monkeypatch.setattr("sys.argv", ["taskbench", "version", "--format", "json"])
    main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["name"] == "Taskbench"


def test_main_format_after_subcommand_table_mode_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``taskbench --format table task search --format table`` shows hint on stderr."""
    argv = ["taskbench", "--format", "table", "task", "search", "--query", "x", "--format", "table"]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "Hint:" in captured.err
    assert "before the subcommand" in captured.err


def test_main_unknown_option_no_format_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown option that isn't --format gets no hint."""
    monkeypatch.setattr("sys.argv", ["taskbench", "version", "--bogus"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert "hint" not in payload


class TestHoistGlobalFormat:
    """--format is accepted in any position (hoisted to the root parser)."""

    def test_trailing_format_pair_hoisted(self):
        from taskbench.cli.main import _hoist_global_format

        assert _hoist_global_format(["task", "list", "--format", "table"]) == [
            "--format",
            "table",
            "task",
            "list",
        ]

    def test_trailing_format_equals_hoisted(self):
        from taskbench.cli.main import _hoist_global_format

        assert _hoist_global_format(["task", "list", "--format=json"]) == ["--format=json", "task", "list"]

    def test_leading_format_untouched(self):
        from taskbench.cli.main import _hoist_global_format

        argv = ["--format", "json", "task", "list"]
        assert _hoist_global_format(argv) == argv

    def test_export_tasks_format_untouched(self):
        from taskbench.cli.main import _hoist_global_format

        argv = ["bulk", "export-tasks", "--list-id", "1", "--format", "csv"]
        assert _hoist_global_format(argv) == argv

    def test_middle_flags_preserved(self):
        from taskbench.cli.main import _hoist_global_format

        assert _hoist_global_format(["task", "list", "--list-id", "5", "--format", "table", "--brief"]) == [
            "--format",
            "table",
            "task",
            "list",
            "--list-id",
            "5",
            "--brief",
        ]

    def test_no_format_untouched(self):
        from taskbench.cli.main import _hoist_global_format

        argv = ["task", "list", "--brief"]
        assert _hoist_global_format(argv) == argv
