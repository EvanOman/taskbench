"""Shared pytest fixtures for ClickUp toolkit tests."""

import os
from unittest.mock import AsyncMock

import pytest

from clickup.core import Config
from clickup.core.client import ClickUpClient
from clickup.core.models import Task, Team, User


@pytest.fixture(autouse=True)
def isolate_clickup_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Prevent CLICKUP_ env leakage between tests (skip for live tests)."""
    if request.node.get_closest_marker("live"):
        yield
        return

    original_keys = [key for key in os.environ if key.startswith("CLICKUP_")]
    for key in original_keys:
        monkeypatch.delenv(key, raising=False)

    yield

    for key in [key for key in os.environ if key.startswith("CLICKUP_")]:
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
