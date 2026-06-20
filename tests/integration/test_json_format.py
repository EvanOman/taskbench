"""JSON-format tests for the migrated commands (issue #15 acceptance).

Each command runs in `--format json` mode and the output is parsed to confirm
the contract shape (`{"data":[...],"count":N}` for collections,
`model_dump(mode="json")` for singletons).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from taskbench.cli.main import app
from taskbench.core.models import (
    Folder,
    Space,
    SpaceRef,
    Team,
    User,
)
from taskbench.core.models import (
    List as ClickUpList,
)

runner = CliRunner()


def _user(**kw):
    base = {"id": 1, "username": "u", "email": "u@x.com", "color": None}
    base.update(kw)
    return User(**base)


def _team(**kw):
    base = {"id": "T1", "name": "Acme", "color": "#000", "members": []}
    base.update(kw)
    return Team(**base)


def _space(**kw):
    base = {"id": "S1", "name": "Eng", "private": False, "statuses": [], "multiple_assignees": True}
    base.update(kw)
    return Space(**base)


def _list(**kw):
    base = {"id": "L1", "name": "Sprint", "task_count": 5}
    base.update(kw)
    return ClickUpList(**base)


def _folder(**kw):
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


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


# ---------- workspace --------------------------------------------------------


@patch("taskbench.cli.commands.workspace.get_client")
def test_workspace_list_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = [_team(), _team(id="T2", name="Other")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "workspace", "list"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert {t["name"] for t in data["data"]} == {"Acme", "Other"}


@patch("taskbench.cli.commands.workspace.get_client")
def test_workspace_spaces_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = [_space()]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "workspace", "spaces", "--workspace-id", "T1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["data"][0]["name"] == "Eng"


@patch("taskbench.cli.commands.workspace.get_client")
def test_workspace_folders_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = [_folder()]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "workspace", "folders", "--space-id", "S1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["data"][0]["name"] == "Backend"


@patch("taskbench.cli.commands.workspace.get_client")
def test_workspace_members_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_team_members.return_value = [_user(id=1, username="a"), _user(id=2, username="b")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "workspace", "members", "--workspace-id", "T1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert {u["username"] for u in data["data"]} == {"a", "b"}


# ---------- discover hierarchy -----------------------------------------------


def _named(**kw):
    name = kw.pop("name", None)
    m = Mock(**kw)
    if name is not None:
        m.name = name
    return m


@patch("taskbench.cli.commands.discover.get_client")
def test_discover_hierarchy_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = [_named(id="T1", name="Acme")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="Eng")]
    mock_client.get_folders.return_value = [_named(id="F1", name="Backend")]
    mock_client.get_lists.return_value = [_named(id="L1", name="Sprint", task_count=5)]
    mock_client.get_folderless_lists.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "discover", "hierarchy", "--depth", "4"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["workspaces"][0]["name"] == "Acme"
    assert data["workspaces"][0]["spaces"][0]["name"] == "Eng"
    assert data["workspaces"][0]["spaces"][0]["folders"][0]["name"] == "Backend"


@patch("taskbench.cli.commands.discover.get_client")
def test_discover_hierarchy_table_no_crash(mock_get_client):
    """Default table mode also works (regression for the Mock(name=...) bug)."""
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = [_named(id="T1", name="Acme")]
    mock_client.get_spaces.return_value = [_named(id="S1", name="Eng")]
    mock_client.get_folders.return_value = []
    mock_client.get_folderless_lists.return_value = []
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["discover", "hierarchy"])
    assert result.exit_code == 0
    assert "Acme" in result.output


# ---------- task list (smoke) ------------------------------------------------


@patch("taskbench.cli.commands.task.get_client")
def test_task_list_json(mock_get_client):
    from taskbench.core.models import Task

    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = [Task(id="t1", name="One"), Task(id="t2", name="Two")]
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "task", "list", "--list-id", "L1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert {t["name"] for t in data["data"]} == {"One", "Two"}


@patch("taskbench.cli.commands.task.get_client")
def test_task_get_json(mock_get_client):
    from taskbench.core.models import Task

    mock_client = AsyncMock()
    mock_client.get_task.return_value = Task(id="t1", name="One", description="d")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["--format", "json", "task", "get", "t1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "One"
