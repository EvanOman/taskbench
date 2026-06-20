"""Pytest configuration and fixtures for live integration tests.

These tests use the actual ClickUp API and require:
- CLICKUP_API_KEY environment variable to be set
- A valid ClickUp workspace with at least one space

Run with: uv run pytest tests/live -v
Skip with: uv run pytest --ignore=tests/live
"""

import os
from collections.abc import AsyncGenerator

import pytest

from taskbench.core import ClickUpClient, Config, Space, Task, Team
from taskbench.core import List as ClickUpList


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "live: marks tests as requiring live API access")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests if CLICKUP_API_KEY is not set."""
    api_key = os.environ.get("CLICKUP_API_KEY") or os.environ.get("CLICKUP_API_TOKEN")
    if not api_key:
        skip_marker = pytest.mark.skip(reason="CLICKUP_API_KEY environment variable not set")
        for item in items:
            if "live" in item.keywords or "tests/live" in str(item.fspath):
                item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def api_key() -> str:
    """Get the API key from environment, or skip tests."""
    key = os.environ.get("CLICKUP_API_KEY") or os.environ.get("CLICKUP_API_TOKEN")
    if not key:
        pytest.skip("CLICKUP_API_KEY environment variable not set")
        raise RuntimeError("unreachable")  # Help type checker understand pytest.skip raises
    return key


@pytest.fixture(scope="session")
def live_config(api_key: str) -> Config:
    """Create a configuration with real API credentials."""
    config = Config()
    # Ensure the API token is set
    if not config.get_api_token():
        config.set_api_token(api_key)
    return config


@pytest.fixture
async def live_client(live_config: Config) -> AsyncGenerator[ClickUpClient, None]:
    """Create a ClickUp client with real API credentials."""
    async with ClickUpClient(live_config) as client:
        yield client


@pytest.fixture(scope="session")
def session_client(live_config: Config) -> ClickUpClient:
    """Session-scoped client for fixtures that need to make API calls."""
    return ClickUpClient(live_config)


@pytest.fixture(scope="module")
async def test_team(live_client: ClickUpClient) -> Team:
    """Get the first available team/workspace for testing."""
    teams = await live_client.get_teams()
    if not teams:
        pytest.skip("No teams/workspaces available for testing")
    return teams[0]


@pytest.fixture(scope="module")
async def test_space(live_client: ClickUpClient, test_team: Team) -> Space:
    """Get the first available space for testing."""
    spaces = await live_client.get_spaces(test_team.id)
    if not spaces:
        pytest.skip("No spaces available for testing")
    return spaces[0]


@pytest.fixture(scope="module")
async def test_list(live_client: ClickUpClient, test_space: Space) -> ClickUpList:
    """Get or create a test list for task operations.

    First tries to get folderless lists, then lists from folders.
    Creates a test list if none exist.
    """
    # Try folderless lists first
    lists = await live_client.get_folderless_lists(test_space.id)
    if lists:
        return lists[0]

    # Try lists from folders
    folders = await live_client.get_folders(test_space.id)
    for folder in folders:
        folder_lists = await live_client.get_lists(folder.id)
        if folder_lists:
            return folder_lists[0]

    # Create a test list if none exist
    test_list = await live_client.create_folderless_list(test_space.id, "Integration Test List - Safe to Delete")
    return test_list


@pytest.fixture
async def test_task(live_client: ClickUpClient, test_list: ClickUpList) -> AsyncGenerator[Task, None]:
    """Create a test task for testing, and clean it up afterward."""
    task = await live_client.create_task(
        test_list.id,
        name="Integration Test Task - Safe to Delete",
        description="This task was created by automated integration tests.",
    )
    yield task
    # Cleanup: delete the task after the test
    try:
        await live_client.delete_task(task.id)
    except Exception:
        pass  # Best effort cleanup


# Module-level markers
pytestmark = pytest.mark.live
