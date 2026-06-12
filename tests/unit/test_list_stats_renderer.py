"""Unit tests for the render_list_stats renderer and updated hint text."""

from __future__ import annotations

import json

import pytest
import typer

from clickup.cli.output import FormatChoice, render_list_stats, set_format


class TestRenderListStatsJson:
    def test_json_envelope(self, capsys):
        set_format(FormatChoice.json)
        rows = [
            {
                "id": "L1",
                "name": "Sprint",
                "space": "Eng",
                "task_count": 5,
                "open_count": 3,
                "last_updated": "2025-01-01T00:00:00Z",
            }
        ]
        render_list_stats(rows)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["count"] == 1
        assert payload["data"][0]["id"] == "L1"
        assert payload["data"][0]["task_count"] == 5
        assert payload["data"][0]["open_count"] == 3
        assert payload["data"][0]["last_updated"] == "2025-01-01T00:00:00Z"

    def test_empty_list(self, capsys):
        set_format(FormatChoice.json)
        render_list_stats([])
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload == {"data": [], "count": 0}

    def test_null_last_updated(self, capsys):
        set_format(FormatChoice.json)
        rows = [
            {
                "id": "L1",
                "name": "Empty",
                "space": "Eng",
                "task_count": 0,
                "open_count": 0,
                "last_updated": None,
            }
        ]
        render_list_stats(rows)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["data"][0]["last_updated"] is None


class TestRenderListStatsTable:
    def test_table_output_has_columns(self, capsys, monkeypatch):
        from io import StringIO

        from rich.console import Console

        from clickup.cli import output

        buf = StringIO()
        monkeypatch.setattr(output, "_console", Console(file=buf, force_terminal=False, width=200))
        set_format(FormatChoice.table)

        rows = [
            {
                "id": "L1",
                "name": "Sprint",
                "space": "Eng",
                "task_count": 5,
                "open_count": 3,
                "last_updated": "2025-01-01T00:00:00Z",
            }
        ]
        render_list_stats(rows)
        table_out = buf.getvalue()
        assert "Sprint" in table_out
        assert "L1" in table_out
        assert "5" in table_out
        assert "3" in table_out

    def test_table_escapes_brackets(self, capsys, monkeypatch):
        """Names with brackets should not be swallowed by Rich markup."""
        from io import StringIO

        from rich.console import Console

        from clickup.cli import output

        buf = StringIO()
        monkeypatch.setattr(output, "_console", Console(file=buf, force_terminal=False, width=200))
        set_format(FormatChoice.table)

        rows = [
            {
                "id": "L1",
                "name": "[bug] tracker",
                "space": "Eng",
                "task_count": 1,
                "open_count": 1,
                "last_updated": None,
            }
        ]
        render_list_stats(rows)
        table_out = buf.getvalue()
        # Rich should not interpret [bug] as markup — the name should appear
        assert "bug" in table_out
        assert "tracker" in table_out


class TestRequireListIdHint:
    def test_hint_mentions_discover(self, capsys):
        """require_list_id hint now mentions 'clickup discover hierarchy'."""
        from clickup.cli.output import set_format
        from clickup.cli.shared import require_list_id

        set_format("json")
        with pytest.raises(typer.Exit) as exc:
            require_list_id(None)
        assert exc.value.exit_code == 2
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert "discover hierarchy" in payload["hint"]


class TestStatusHelpText:
    def test_status_help_mentions_authenticated(self):
        """status command help text mentions 'authenticated user'."""
        from typer.testing import CliRunner

        from clickup.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "authenticated" in result.stdout.lower()
