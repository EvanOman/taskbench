"""Unit tests for read-time folder enrichment in the JSON provider.

Validates that ``get_folder`` / ``get_folders`` populate child lists and
compute ``task_count`` from live store data, so reads always reflect the
latest state regardless of what was stored at write time.
"""

import pytest

from taskbench.core import Config
from taskbench.core.json_provider import JsonProvider, write_seed_store


@pytest.fixture()
def provider(tmp_path, monkeypatch):
    """Return a ready-to-use JsonProvider backed by a tmp seed store."""
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
    store_path = tmp_path / "mock-store.json"
    write_seed_store(store_path)
    config = Config()
    config.set("json_store_path", str(store_path))
    return JsonProvider(config)


@pytest.mark.asyncio
async def test_folder_get_reflects_newly_created_child_list(provider):
    """After creating a list inside a folder, ``get_folder`` includes it."""
    async with provider as p:
        # Seed folder starts with two child lists (list_inbox, list_active).
        folder = await p.get_folder("folder_daily")
        assert len(folder.lists) == 2
        original_ids = {lst.id for lst in folder.lists}

        # Create a new list inside the same folder.
        new_list = await p.create_list("folder_daily", "Backlog")

        # Re-fetch: the new list must appear.
        folder = await p.get_folder("folder_daily")
        assert len(folder.lists) == 3
        refreshed_ids = {lst.id for lst in folder.lists}
        assert new_list.id in refreshed_ids
        assert original_ids < refreshed_ids


@pytest.mark.asyncio
async def test_folder_task_count_rolls_up_after_task_creation(provider):
    """``task_count`` sums tasks across all child lists, stringified."""
    async with provider as p:
        # Seed store: list_inbox has 3 tasks, list_active has 2 → total 5.
        folder = await p.get_folder("folder_daily")
        assert folder.task_count == "5"

        # Add a task to list_inbox.
        await p.create_task("list_inbox", "Extra task")
        folder = await p.get_folder("folder_daily")
        assert folder.task_count == "6"

        # Add a task to list_active.
        await p.create_task("list_active", "Another extra")
        folder = await p.get_folder("folder_daily")
        assert folder.task_count == "7"


@pytest.mark.asyncio
async def test_get_folders_enriches_all_returned_folders(provider):
    """``get_folders`` enriches every folder, not just the first."""
    async with provider as p:
        # Create a second folder with a list and a task.
        new_folder = await p.create_folder("space_ops", "Projects")
        new_list = await p.create_list(new_folder.id, "Sprint")
        await p.create_task(new_list.id, "Ship it")

        folders = await p.get_folders("space_ops")
        by_id = {f.id: f for f in folders}

        daily = by_id["folder_daily"]
        assert len(daily.lists) == 2
        assert daily.task_count == "5"  # unchanged seed data

        projects = by_id[new_folder.id]
        assert len(projects.lists) == 1
        assert projects.lists[0].id == new_list.id
        assert projects.task_count == "1"


@pytest.mark.asyncio
async def test_empty_folder_has_zero_task_count(provider):
    """A folder with no child lists reports task_count '0'."""
    async with provider as p:
        empty = await p.create_folder("space_ops", "Empty")
        folder = await p.get_folder(empty.id)
        assert folder.lists == []
        assert folder.task_count == "0"
