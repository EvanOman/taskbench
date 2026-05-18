"""Integration coverage for the local JSON provider."""

import json

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core import Config
from clickup.core.exceptions import NotFoundError, ValidationError
from clickup.core.json_provider import JsonProvider, write_seed_store

runner = CliRunner()


def test_mock_init_configures_json_provider_and_task_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"

    result = runner.invoke(app, ["mock", "init", "--path", str(store_path)])

    assert result.exit_code == 0
    assert store_path.exists()

    result = runner.invoke(app, ["task", "list", "--list-id", "inbox"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3
    assert data["data"][0]["id"].startswith("mock_")

    result = runner.invoke(
        app,
        ["task", "create", "Write local provider test note", "--list-id", "active", "--status", "on-deck"],
    )
    assert result.exit_code == 0
    created = json.loads(result.stdout)
    assert created["name"] == "Write local provider test note"
    assert created["status"]["status"] == "on-deck"

    result = runner.invoke(app, ["task", "status", created["id"], "complete"])
    assert result.exit_code == 0
    updated = json.loads(result.stdout)
    assert updated["status"]["status"] == "complete"


def test_mock_init_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"

    first = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    second = runner.invoke(app, ["mock", "init", "--path", str(store_path)])

    assert first.exit_code == 0
    assert second.exit_code == 2
    assert "already exists" in second.stderr


@pytest.mark.asyncio
async def test_json_provider_workspace_and_list_methods(tmp_path, monkeypatch):
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    write_seed_store(store_path)
    config = Config()
    config.set("json_store_path", str(store_path))

    async with JsonProvider(config) as provider:
        user = await provider.get_user()
        assert user.username == "Mock Agent"
        ok, message, validated_user = await provider.validate_auth()
        assert ok is True
        assert "Local JSON provider active" in message
        assert validated_user == user

        teams = await provider.get_teams()
        assert teams[0].id == "team_mock"
        assert (await provider.get_team("team_mock")).name == "Mock Workspace"
        assert (await provider.get_team_members("team_mock"))[0].email == "agent@example.test"

        spaces = await provider.get_spaces("team_mock")
        assert spaces[0].id == "space_ops"
        assert (await provider.get_space("space_ops")).name == "Operations"

        folders = await provider.get_folders("space_ops")
        assert folders[0].id == "folder_daily"
        assert (await provider.get_folder("folder_daily")).name == "Daily Work"

        lists = await provider.get_lists("folder_daily")
        assert [item.id for item in lists] == ["list_inbox", "list_active"]
        assert (await provider.get_list("list_inbox")).name == "Inbox"
        assert await provider.get_folderless_lists("space_ops") == []


@pytest.mark.asyncio
async def test_json_provider_task_mutations_comments_search_and_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    write_seed_store(store_path)
    config = Config()
    config.set("json_store_path", str(store_path))

    async with JsonProvider(config) as provider:
        raw_teams = await provider.raw_request("GET", "/team")
        assert raw_teams["teams"][0]["id"] == "team_mock"
        raw_list = await provider.raw_request("GET", "/list/list_inbox")
        assert raw_list["name"] == "Inbox"
        raw_tasks = await provider.raw_request("GET", "/list/list_inbox/task", params={"statuses": ["to do"]})
        assert len(raw_tasks["tasks"]) == 2
        raw_task = await provider.raw_request("GET", "/task/mock_1001")
        assert raw_task["name"] == "Draft weekly project update"

        task = await provider.create_task("list_inbox", "Call design partner", status="to do", priority=1)
        assert task.id == "mock_1006"
        assert task.priority is not None
        assert task.priority.priority == "1"

        updated = await provider.update_task(task.id, status="complete", description="Done", priority=4)
        assert updated.status is not None
        assert updated.status.status == "complete"
        assert updated.description == "Done"
        assert updated.priority is not None
        assert updated.priority.priority == "4"

        comments = await provider.get_task_comments("mock_1001")
        assert comments[0].comment_text == "Use concise bullets."
        comment = await provider.create_comment(task.id, "Finished in local test")
        assert comment.comment_text == "Finished in local test"

        results = await provider.search_tasks("team_mock", "design partner")
        assert [item.id for item in results] == [task.id]

        assert await provider.delete_task(task.id) is True
        with pytest.raises(NotFoundError):
            await provider.get_task(task.id)


@pytest.mark.asyncio
async def test_json_provider_list_creation_and_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    write_seed_store(store_path)
    config = Config()
    config.set("json_store_path", str(store_path))

    async with JsonProvider(config) as provider:
        folder_list = await provider.create_list("folder_daily", "Later")
        assert folder_list.name == "Later"
        folderless = await provider.create_folderless_list("space_ops", "Ideas")
        assert folderless.name == "Ideas"

        with pytest.raises(NotFoundError):
            await provider.get_team("missing")
        with pytest.raises(NotFoundError):
            await provider.get_space("missing")
        with pytest.raises(NotFoundError):
            await provider.get_folder("missing")
        with pytest.raises(NotFoundError):
            await provider.get_list("missing")
        with pytest.raises(NotFoundError):
            await provider.create_list("missing", "Nope")
        with pytest.raises(NotFoundError):
            await provider.create_folderless_list("missing", "Nope")
        with pytest.raises(NotFoundError):
            await provider.delete_task("missing")
        with pytest.raises(ValidationError):
            await provider.raw_request("PATCH", "/unsupported")
