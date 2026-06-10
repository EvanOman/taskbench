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


@pytest.mark.asyncio
async def test_json_provider_rejects_unknown_status_on_update(tmp_path, monkeypatch):
    """JsonProvider should validate status names against the list's statuses,
    matching the real ClickUp API's behavior (issue #29 P0 #4 / Agent 15)."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    write_seed_store(store_path)
    config = Config()
    config.set("json_store_path", str(store_path))

    async with JsonProvider(config) as provider:
        with pytest.raises(ValidationError, match="Unknown status"):
            await provider.update_task("mock_1001", status="xyzzy-not-a-real-status")
        with pytest.raises(ValidationError, match="Unknown status"):
            await provider.create_task("list_inbox", "Test", status="nope")


def test_task_list_brief_flag_strips_noisy_fields(tmp_path, monkeypatch):
    """--brief returns an agent-routing projection, not the 30-field default."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    result = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    assert result.exit_code == 0

    result = runner.invoke(app, ["task", "list", "--list-id", "inbox", "--brief"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] >= 1
    sample = data["data"][0]
    # Brief keeps these identity/routing fields.
    for required in ("id", "name", "status", "list", "url"):
        assert required in sample, f"--brief missing key {required!r}"
    # And drops the noisy ones.
    for absent in ("text_content", "watchers", "checklists", "tags", "custom_fields", "dependencies"):
        assert absent not in sample, f"--brief should drop {absent!r}, found {sample[absent]!r}"


def test_task_list_open_only_excludes_closed(tmp_path, monkeypatch):
    """--open-only drops tasks whose status type is 'closed'."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    result = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    assert result.exit_code == 0

    # Close one task so the filter has something to drop.
    result = runner.invoke(app, ["task", "status", "mock_1001", "complete"])
    assert result.exit_code == 0

    everything = json.loads(runner.invoke(app, ["task", "list", "--list-id", "inbox"]).stdout)
    open_only = json.loads(runner.invoke(app, ["task", "list", "--list-id", "inbox", "--open-only"]).stdout)

    assert any(t["id"] == "mock_1001" for t in everything["data"])
    assert not any(t["id"] == "mock_1001" for t in open_only["data"]), "closed task leaked through --open-only"
    assert open_only["count"] == everything["count"] - 1


def test_task_update_description_append(tmp_path, monkeypatch):
    """--description-append concatenates instead of overwriting."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    result = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    assert result.exit_code == 0

    original = json.loads(runner.invoke(app, ["task", "get", "mock_1001"]).stdout)["description"]
    assert original  # seed has a description

    result = runner.invoke(app, ["task", "update", "mock_1001", "--description-append", " — due Friday"])
    assert result.exit_code == 0
    updated = json.loads(result.stdout)["description"]
    assert updated == original + " — due Friday"


def test_task_update_description_and_append_are_mutually_exclusive():
    """--description and --description-append cannot both be passed."""
    result = runner.invoke(app, ["task", "update", "mock_1001", "--description", "x", "--description-append", "y"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.stderr


def test_task_mine_filter_parity_status_and_open_only(tmp_path, monkeypatch):
    """`task mine` honors --status / --open-only just like `task list` does."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    result = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    assert result.exit_code == 0

    # Seed has the Mock Agent as user id=1 but no tasks are auto-assigned.
    # Assign mock_1001 to user 1, leave others unassigned.
    result = runner.invoke(
        app,
        ["task", "update", "mock_1001", "--status", "in progress"],
    )
    assert result.exit_code == 0
    # Pre-condition: the search_tasks API in JsonProvider doesn't filter by
    # assignee, so `task mine` returns all tasks matching the query "". That
    # means we can validate the post-filter (--status / --open-only) logic
    # without needing real assignee plumbing.
    result = runner.invoke(app, ["task", "mine", "--status", "in progress"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert all(t["status"]["status"] == "in progress" for t in data["data"])


def test_batch_status_change_partial_failure(tmp_path, monkeypatch):
    """`task done T_good T_bad` updates the good task, reports the bad one, exits 1."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    result = runner.invoke(app, ["mock", "init", "--path", str(tmp_path / "store.json")])
    assert result.exit_code == 0

    result = runner.invoke(app, ["task", "done", "mock_1001", "mock_9999"])
    assert result.exit_code == 1
    # Successful update still lands on stdout as the usual envelope.
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["data"][0]["id"] == "mock_1001"
    assert data["data"][0]["status"]["status"] == "complete"
    # The failure is a canonical error envelope on stderr.
    err = json.loads(result.stderr.strip().splitlines()[-1])
    assert err["type"] == "NotFoundError"
    assert "mock_9999" in err["error"]


def test_batch_status_change_all_fail(tmp_path, monkeypatch):
    """All-bad batch keeps stdout empty (no data envelope) and exits 1."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    result = runner.invoke(app, ["mock", "init", "--path", str(tmp_path / "store.json")])
    assert result.exit_code == 0

    result = runner.invoke(app, ["task", "done", "mock_9998", "mock_9999"])
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    error_lines = [json.loads(line) for line in result.stderr.strip().splitlines() if line.startswith("{")]
    assert len(error_lines) == 2
    assert all(e["type"] == "NotFoundError" for e in error_lines)


def test_batch_status_change_all_succeed_unchanged(tmp_path, monkeypatch):
    """Happy-path batch keeps the existing envelope shape and exit 0."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    result = runner.invoke(app, ["mock", "init", "--path", str(tmp_path / "store.json")])
    assert result.exit_code == 0

    result = runner.invoke(app, ["task", "done", "mock_1001", "mock_1002"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    assert {t["id"] for t in data["data"]} == {"mock_1001", "mock_1002"}


def test_task_objects_carry_comment_count(tmp_path, monkeypatch):
    """JsonProvider annotates comment_count so audits don't need N+1 calls."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    result = runner.invoke(app, ["mock", "init", "--path", str(tmp_path / "store.json")])
    assert result.exit_code == 0

    data = json.loads(runner.invoke(app, ["task", "list", "--list-id", "inbox"]).stdout)
    counts = {t["id"]: t["comment_count"] for t in data["data"]}
    assert counts["mock_1001"] == 1  # seed store has one comment here
    assert counts["mock_1003"] == 0

    result = runner.invoke(app, ["task", "comments", "add", "mock_1003", "audit note"])
    assert result.exit_code == 0
    after = json.loads(runner.invoke(app, ["task", "get", "mock_1003"]).stdout)
    assert after["comment_count"] == 1

    # --brief keeps the field too.
    brief = json.loads(runner.invoke(app, ["task", "get", "mock_1003", "--brief"]).stdout)
    assert brief["comment_count"] == 1
