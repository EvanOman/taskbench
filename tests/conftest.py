"""Shared pytest fixtures for Taskbench tests."""

import os
from unittest.mock import AsyncMock

import pytest

from taskbench.core import Config
from taskbench.core.client import ClickUpClient
from taskbench.core.models import Task, Team, User


@pytest.fixture(autouse=True)
def isolate_clickup_env(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
):
    """Isolate every test from the user's real env vars and config file.

    A bare `Config()` (no path argument) writes to ~/.config/taskbench/config.json
    in production. Several tests instantiate Config that way and call .set(...), which
    would persist to the real user config. We redirect _get_default_config_path here
    so those writes go to a per-test tmp path. Live-marked tests skip isolation so they
    keep their real env access.
    """
    if request.node.get_closest_marker("live"):
        yield
        return

    # Strip both TASKBENCH_* (new generic) and CLICKUP_* (backend-specific) env vars
    original_keys = [key for key in os.environ if key.startswith(("CLICKUP_", "TASKBENCH_"))]
    for key in original_keys:
        monkeypatch.delenv(key, raising=False)

    tmp_config = tmp_path_factory.mktemp("taskbench-config") / "config.json"
    monkeypatch.setattr(Config, "_get_default_config_path", lambda self: tmp_config, raising=True)
    monkeypatch.setattr(Config, "_get_config_path", lambda self: str(tmp_config), raising=True)

    yield

    for key in [key for key in os.environ if key.startswith(("CLICKUP_", "TASKBENCH_"))]:
        os.environ.pop(key, None)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary config directory for config tests."""
    return tmp_path


@pytest.fixture
def mock_config(tmp_path):
    """Create a test configuration with an explicit API token."""
    config = Config(config_path=tmp_path / "config.json")
    config.set_api_token("test_token")
    return config


@pytest.fixture
def mock_clickup_client(mock_config):
    """Create a ClickUp client with a mocked HTTP client."""
    client = ClickUpClient(mock_config)
    client.client = AsyncMock()
    return client


@pytest.fixture
def sample_task():
    """Provide a minimal Task model for client tests."""
    return Task(id="task123", name="Test Task")


@pytest.fixture
def sample_team():
    """Provide a minimal Team model for client tests."""
    return Team(id="team123", name="Test Team", color="#ff0000", members=[])


@pytest.fixture
def sample_user():
    """Provide a minimal User model for client tests."""
    return User(id=1, username="tester", email="tester@example.com")
