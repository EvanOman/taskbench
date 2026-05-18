"""Tests for the Typer/Click error JSON envelope wrapper in main()."""

from __future__ import annotations

import json

import click
import pytest

from clickup.cli.main import _emit_click_error_envelope, _wants_json_mode, main


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
        (["task", "list", "--format", "json"], True),  # flag after subcommand still detected
    ],
)
def test_wants_json_mode_parses_argv(argv: list[str], expected: bool) -> None:
    assert _wants_json_mode(argv) is expected


def test_emit_click_error_envelope_shape(capsys: pytest.CaptureFixture[str]) -> None:
    """The envelope carries error, type, and (when available) command path."""
    exc = click.exceptions.UsageError("No such command 'frobnicate'.")
    # ctx is None for top-level errors; envelope should omit command then.
    _emit_click_error_envelope(exc)
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {"error": "No such command 'frobnicate'.", "type": "UsageError"}


def test_emit_click_error_envelope_with_context(capsys: pytest.CaptureFixture[str]) -> None:
    cmd = click.Command(name="list")
    ctx = click.Context(cmd, info_name="list", parent=click.Context(click.Command(name="clickup"), info_name="clickup"))
    exc = click.exceptions.BadParameter("not a valid integer", ctx=ctx, param_hint="'--limit'")
    _emit_click_error_envelope(exc)
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error"].startswith("Invalid value for '--limit'")
    assert payload["type"] == "BadParameter"
    assert payload["command"] == "clickup list"


def test_main_emits_json_envelope_for_unknown_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: `clickup frobnicate` should exit 2 with a JSON error on stderr."""
    monkeypatch.setattr("sys.argv", ["clickup", "frobnicate"])
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
    """`clickup task list --list-id L --limit abc` → JSON envelope, exit 2."""
    monkeypatch.setattr("sys.argv", ["clickup", "task", "list", "--list-id", "L", "--limit", "abc"])
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
    monkeypatch.setattr("sys.argv", ["clickup", "--format", "table", "frobnicate"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    # Click's default format includes "No such command" prose on stderr.
    assert "frobnicate" in captured.err
    # Crucially, NOT a JSON envelope.
    assert not captured.err.lstrip().startswith("{")
