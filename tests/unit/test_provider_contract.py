"""Provider contract parity tests.

Ensures that every concrete TaskProvider adapter satisfies the Protocol
contract.  JsonProvider is exercised end-to-end (it can run without a
network); ClickUpClient is verified via structural typing conformance.
"""

from __future__ import annotations

import json

import pytest

from clickup.core.client import ClickUpClient
from clickup.core.json_provider import JsonProvider, seed_store
from clickup.core.models import Comment, Task

# ---------------------------------------------------------------------------
# Structural conformance — compile-time (ty) plus runtime check
# ---------------------------------------------------------------------------


def test_json_provider_is_task_provider():
    """JsonProvider structurally satisfies TaskProvider."""
    assert issubclass(JsonProvider, type) or True  # structural protocols are duck-typed
    # The real check: every abstract method on the protocol exists on the adapter.
    for attr in (
        "__aenter__",
        "__aexit__",
        "raw_request",
        "get_user",
        "validate_auth",
        "get_teams",
        "get_team",
        "get_team_members",
        "get_spaces",
        "get_space",
        "get_folders",
        "get_folder",
        "create_folder",
        "get_lists",
        "get_folderless_lists",
        "get_list",
        "create_list",
        "create_folderless_list",
        "get_tasks",
        "get_task",
        "create_task",
        "update_task",
        "delete_task",
        "get_task_comments",
        "create_comment",
        "search_tasks",
    ):
        assert hasattr(JsonProvider, attr), f"JsonProvider missing {attr}"


def test_clickup_client_is_task_provider():
    """ClickUpClient structurally satisfies TaskProvider."""
    for attr in (
        "__aenter__",
        "__aexit__",
        "raw_request",
        "get_user",
        "validate_auth",
        "get_teams",
        "get_team",
        "get_team_members",
        "get_spaces",
        "get_space",
        "get_folders",
        "get_folder",
        "create_folder",
        "get_lists",
        "get_folderless_lists",
        "get_list",
        "create_list",
        "create_folderless_list",
        "get_tasks",
        "get_task",
        "create_task",
        "update_task",
        "delete_task",
        "get_task_comments",
        "create_comment",
        "search_tasks",
    ):
        assert hasattr(ClickUpClient, attr), f"ClickUpClient missing {attr}"


# ---------------------------------------------------------------------------
# JsonProvider round-trip contract tests
# ---------------------------------------------------------------------------


@pytest.fixture
def json_store(tmp_path, monkeypatch):
    """Seed a temp JSON store and configure the provider to use it."""
    store_path = tmp_path / "store.json"
    store_path.write_text(json.dumps(seed_store()))
    monkeypatch.setenv("CLICKUP_JSON_STORE", str(store_path))
    monkeypatch.setenv("CLICKUP_PROVIDER", "json")
    return store_path


@pytest.fixture
def list_id():
    """Default list_id used in the seeded store."""
    return "list_inbox"


@pytest.mark.asyncio
async def test_create_then_get_round_trip(json_store, list_id):
    """create_task followed by get_task returns the same task."""
    async with JsonProvider() as p:
        created = await p.create_task(list_id, "Round-trip task", description="hello")
        assert isinstance(created, Task)
        assert created.name == "Round-trip task"
        assert created.description == "hello"

        fetched = await p.get_task(created.id)
        assert fetched.id == created.id
        assert fetched.name == created.name
        assert fetched.description == created.description


@pytest.mark.asyncio
async def test_update_task_modify_if_passed(json_store, list_id):
    """Only the passed fields are changed; unpassed fields remain untouched."""
    async with JsonProvider() as p:
        created = await p.create_task(list_id, "Original name", description="keep me")

        updated = await p.update_task(created.id, name="New name")
        assert updated.name == "New name"
        assert updated.description == "keep me"  # untouched


@pytest.mark.asyncio
async def test_update_task_clear_description(json_store, list_id):
    """Passing description=None clears the description."""
    async with JsonProvider() as p:
        created = await p.create_task(list_id, "Task", description="will be cleared")
        updated = await p.update_task(created.id, description=None)
        assert updated.description is None


@pytest.mark.asyncio
async def test_delete_task(json_store, list_id):
    """delete_task removes the task; subsequent get raises."""
    from clickup.core.exceptions import NotFoundError

    async with JsonProvider() as p:
        created = await p.create_task(list_id, "Ephemeral")
        assert await p.delete_task(created.id) is True

        with pytest.raises(NotFoundError):
            await p.get_task(created.id)


@pytest.mark.asyncio
async def test_get_tasks(json_store, list_id):
    """get_tasks returns tasks in the given list."""
    async with JsonProvider() as p:
        await p.create_task(list_id, "A")
        await p.create_task(list_id, "B")
        tasks = await p.get_tasks(list_id)
        names = {t.name for t in tasks}
        assert "A" in names
        assert "B" in names


@pytest.mark.asyncio
async def test_comments_round_trip(json_store, list_id):
    """create_comment followed by get_task_comments returns the comment."""
    async with JsonProvider() as p:
        task = await p.create_task(list_id, "Commentable")
        comment = await p.create_comment(task.id, "Hello world")
        assert isinstance(comment, Comment)

        comments = await p.get_task_comments(task.id)
        assert len(comments) >= 1
        assert any(c.comment_text == "Hello world" for c in comments)


@pytest.mark.asyncio
async def test_search_tasks(json_store, list_id):
    """search_tasks matches by substring in name."""
    async with JsonProvider() as p:
        await p.create_task(list_id, "Needle in haystack")
        results = await p.search_tasks("team_mock", "Needle")
        assert any(t.name == "Needle in haystack" for t in results)
