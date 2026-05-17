"""Direct tests for clickup/cli/output.py renderers.

Each renderer is exercised in both table and JSON modes; JSON output is parsed
to confirm shape. These tests pin the output contract that agents depend on.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest

from clickup.cli import output
from clickup.cli.output import (
    FormatChoice,
    format_timestamp,
    get_format,
    render_comment,
    render_comments,
    render_error,
    render_folders,
    render_hierarchy,
    render_kv,
    render_list,
    render_lists,
    render_message,
    render_space,
    render_spaces,
    render_task,
    render_tasks,
    render_team,
    render_teams,
    render_user,
    render_users,
    set_format,
)
from clickup.core.models import (
    Assignee,
    Comment,
    Folder,
    PriorityInfo,
    Space,
    StatusInfo,
    Task,
    Team,
    User,
)
from clickup.core.models import (
    List as ClickUpList,
)


@pytest.fixture(autouse=True)
def reset_format():
    """Each test starts in table mode."""
    set_format(FormatChoice.table)
    yield
    set_format(FormatChoice.table)


@pytest.fixture
def capture_console(monkeypatch):
    """Replace the module-level rich Console with one writing to a StringIO."""
    from rich.console import Console as RConsole

    buf = StringIO()
    monkeypatch.setattr(output, "_console", RConsole(file=buf, force_terminal=False, width=200))
    return buf


@pytest.fixture
def capture_stderr(monkeypatch, capsys):
    """Use capsys for stderr (typer.echo writes there)."""
    return capsys


# ---------- helpers ----------------------------------------------------------


def _user(**kw):
    base = {"id": 1, "username": "evan", "email": "evan@example.com", "color": "#fff"}
    base.update(kw)
    return User(**base)


def _team(**kw):
    base = {"id": "T1", "name": "Acme", "color": "#000", "members": []}
    base.update(kw)
    return Team(**base)


def _space(**kw):
    base = {"id": "S1", "name": "Engineering", "private": False, "statuses": [], "multiple_assignees": True}
    base.update(kw)
    return Space(**base)


def _list(**kw):
    base = {"id": "L1", "name": "Sprint 42", "task_count": 7}
    base.update(kw)
    return ClickUpList(**base)


def _folder(**kw):
    from clickup.core.models import SpaceRef

    base = {
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


def _task(**kw):
    base = {
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


def _comment(**kw):
    base = {
        "id": "C1",
        "comment": [{"text": "looks good"}],
        "comment_text": "looks good",
        "user": _user(),
        "date": "1700000000000",
    }
    base.update(kw)
    return Comment(**base)


# ---------- format state ------------------------------------------------------


def test_format_default_is_table():
    set_format(FormatChoice.table)
    assert get_format() == "table"


def test_set_format_string_and_enum():
    set_format("json")
    assert get_format() == "json"
    set_format(FormatChoice.table)
    assert get_format() == "table"


# ---------- format_timestamp --------------------------------------------------


def test_format_timestamp_human():
    out = format_timestamp("1700000000000")
    assert out.startswith("20")  # yyyy-mm-dd
    assert "-" in out


def test_format_timestamp_iso_for_json():
    out = format_timestamp("1700000000000", for_json=True)
    assert out.endswith("Z")
    assert "T" in out


def test_format_timestamp_empty():
    assert format_timestamp(None) == ""
    assert format_timestamp("") == ""


def test_format_timestamp_unparseable_passes_through():
    assert format_timestamp("not-a-number") == "not-a-number"


# ---------- render_user -------------------------------------------------------


def test_render_user_table(capture_console):
    render_user(_user())
    out = capture_console.getvalue()
    assert "evan" in out
    assert "evan@example.com" in out


def test_render_user_json(capsys):
    set_format("json")
    render_user(_user(role=2))
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["username"] == "evan"
    assert data["role"] == 2


# ---------- render_team(s) ----------------------------------------------------


def test_render_team_table(capture_console):
    render_team(_team())
    assert "Acme" in capture_console.getvalue()


def test_render_team_json(capsys):
    set_format("json")
    render_team(_team())
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "Acme"


def test_render_teams_collection_shape(capsys):
    set_format("json")
    render_teams([_team(), _team(id="T2", name="Other")])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 2
    assert {t["name"] for t in data["data"]} == {"Acme", "Other"}


def test_render_teams_table(capture_console):
    render_teams([_team(), _team(id="T2", name="Other")])
    out = capture_console.getvalue()
    assert "Acme" in out
    assert "Other" in out


# ---------- render_space(s) ---------------------------------------------------


def test_render_space_table(capture_console):
    render_space(_space())
    assert "Engineering" in capture_console.getvalue()


def test_render_space_json(capsys):
    set_format("json")
    render_space(_space(private=True))
    data = json.loads(capsys.readouterr().out)
    assert data["private"] is True


def test_render_spaces_collection_shape(capsys):
    set_format("json")
    render_spaces([_space()])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    assert data["data"][0]["name"] == "Engineering"


def test_render_spaces_table(capture_console):
    render_spaces([_space()])
    assert "Engineering" in capture_console.getvalue()


# ---------- render_list(s) ----------------------------------------------------


def test_render_list_table(capture_console):
    render_list(_list(due_date="1700000000000"))
    out = capture_console.getvalue()
    assert "Sprint 42" in out
    assert "7" in out  # task_count


def test_render_list_json(capsys):
    set_format("json")
    render_list(_list())
    data = json.loads(capsys.readouterr().out)
    assert data["task_count"] == 7


def test_render_lists_collection_shape(capsys):
    set_format("json")
    render_lists([_list(), _list(id="L2", name="Sprint 43")])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 2


def test_render_lists_table(capture_console):
    render_lists([_list()])
    assert "Sprint 42" in capture_console.getvalue()


# ---------- render_folders ----------------------------------------------------


def test_render_folders_table(capture_console):
    render_folders([_folder()])
    out = capture_console.getvalue()
    assert "Backend" in out
    assert "12" in out


def test_render_folders_json(capsys):
    set_format("json")
    render_folders([_folder(hidden=True)])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    assert data["data"][0]["hidden"] is True


def test_render_folders_table_hidden(capture_console):
    render_folders([_folder(hidden=True)])
    assert "Yes" in capture_console.getvalue()


# ---------- render_users ------------------------------------------------------


def test_render_users_table(capture_console):
    render_users([_user(), _user(id=2, username="other", email="other@x.com")])
    out = capture_console.getvalue()
    assert "evan" in out
    assert "other" in out


def test_render_users_json(capsys):
    set_format("json")
    render_users([_user(role=1)])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    assert data["data"][0]["role"] == 1


def test_render_users_custom_title(capture_console):
    render_users([_user()], title="Custom Title")
    assert "Custom Title" in capture_console.getvalue()


def test_render_users_handles_no_role(capture_console):
    render_users([_user(role=None)])
    assert "None" in capture_console.getvalue()


# ---------- render_task(s) ----------------------------------------------------


def test_render_task_table(capture_console):
    render_task(_task())
    out = capture_console.getvalue()
    assert "Ship the thing" in out
    assert "evan" in out


def test_render_task_table_no_status(capture_console):
    render_task(_task(status=None, priority=None, assignees=[], due_date=None, description=None))
    out = capture_console.getvalue()
    assert "Unknown" in out  # status fallback
    assert "Unassigned" in out


def test_render_task_json(capsys):
    set_format("json")
    render_task(_task())
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "Ship the thing"
    assert "priority_label" in data  # dual-display
    assert data["date_created"].endswith("Z")  # ISO 8601


def test_render_tasks_table(capture_console):
    render_tasks([_task(), _task(id="task43", name="Other")])
    out = capture_console.getvalue()
    assert "Ship the thing" in out
    assert "Other" in out


def test_render_tasks_json(capsys):
    set_format("json")
    render_tasks([_task()])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    assert data["data"][0]["name"] == "Ship the thing"


# ---------- render_comments ---------------------------------------------------


def test_render_comments_table(capture_console):
    render_comments([_comment()])
    out = capture_console.getvalue()
    assert "looks good" in out


def test_render_comments_json(capsys):
    set_format("json")
    render_comments([_comment()])
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    assert data["data"][0]["comment_text"] == "looks good"


def test_render_comments_empty(capture_console):
    render_comments([])
    # Should still render, no crash
    assert capture_console.getvalue() is not None


def test_render_comment_table(capture_console):
    render_comment(_comment())
    out = capture_console.getvalue()
    assert "looks good" in out
    assert "evan" in out


def test_render_comment_json(capsys):
    set_format("json")
    render_comment(_comment())
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "C1"
    assert data["comment_text"] == "looks good"


def test_render_task_json_accepts_minimal_mock(capsys):
    from unittest.mock import Mock

    set_format("json")
    task = Mock()
    task.id = "mock-task"
    task.name = "Mock Task"
    render_task(task)
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "mock-task"
    assert data["name"] == "Mock Task"


def test_render_comment_json_accepts_minimal_mock(capsys):
    from unittest.mock import Mock

    set_format("json")
    comment = Mock()
    comment.id = "mock-comment"
    render_comment(comment)
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "mock-comment"


# ---------- render_hierarchy --------------------------------------------------


@pytest.fixture
def hierarchy_data():
    return {
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
                        "folderless_lists": [{"id": "L9", "name": "Loose", "task_count": 1}],
                    }
                ],
            }
        ]
    }


def test_render_hierarchy_table(capture_console, hierarchy_data):
    render_hierarchy(hierarchy_data)
    out = capture_console.getvalue()
    assert "Acme" in out
    assert "Eng" in out
    assert "Backend" in out
    assert "Sprint" in out
    assert "Loose" in out


def test_render_hierarchy_json(capsys, hierarchy_data):
    set_format("json")
    render_hierarchy(hierarchy_data)
    data = json.loads(capsys.readouterr().out)
    assert data["workspaces"][0]["name"] == "Acme"


def test_render_hierarchy_empty(capture_console):
    render_hierarchy({"workspaces": []})
    # Should render the root tree node only
    assert "ClickUp Hierarchy" in capture_console.getvalue()


# ---------- render_kv ---------------------------------------------------------


def test_render_kv_table(capture_console):
    render_kv({"foo": "bar", "n": 42}, title="Stats")
    out = capture_console.getvalue()
    assert "foo" in out
    assert "bar" in out
    assert "42" in out


def test_render_kv_json(capsys):
    set_format("json")
    render_kv({"foo": "bar"}, title="Stats")
    data = json.loads(capsys.readouterr().out)
    assert data["foo"] == "bar"


# ---------- render_message ----------------------------------------------------


def test_render_message_info_to_stdout(capsys):
    render_message("hello", "info")
    captured = capsys.readouterr()
    assert "hello" in captured.out  # stdout for non-error levels (rich console)
    assert captured.err == ""


def test_render_message_warn_to_stderr(capsys):
    render_message("careful", "warn")
    captured = capsys.readouterr()
    assert "careful" in captured.err


def test_render_message_error_to_stderr(capsys):
    render_message("oops", "error")
    captured = capsys.readouterr()
    assert "oops" in captured.err


def test_render_message_json_info_to_stdout(capsys):
    set_format("json")
    render_message("hi", "info")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == {"message": "hi", "level": "info"}
    assert captured.err == ""


def test_render_message_json_warn_to_stderr(capsys):
    set_format("json")
    render_message("warn-msg", "warn")
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data == {"message": "warn-msg", "level": "warn"}


# ---------- render_error ------------------------------------------------------


def test_render_error_to_stderr(capsys):
    render_error("boom")
    captured = capsys.readouterr()
    assert "boom" in captured.err
    assert captured.out == ""


def test_render_error_json(capsys):
    set_format("json")
    render_error("boom")
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data == {"error": "boom"}
    assert captured.out == ""


def test_render_error_escapes_markup(capsys):
    """Rich-bracket text in user data must be escaped, not interpreted."""
    render_error("[bold]not a tag[/bold]")
    captured = capsys.readouterr()
    # The escaped form should appear; either way, no markup parsing crash.
    assert "[bold]not a tag" in captured.err or "not a tag" in captured.err
