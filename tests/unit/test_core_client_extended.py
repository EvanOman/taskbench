"""Extended unit tests for core client functionality."""

from unittest.mock import AsyncMock, Mock

import pytest

from taskbench.core.client import ClickUpClient
from taskbench.core.config import Config
from taskbench.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    """Create a test configuration."""
    monkeypatch.setenv("CLICKUP_API_KEY", "test_token")
    config = Config(config_path=tmp_path / "config.json")
    return config


@pytest.fixture
def client(mock_config):
    """Create a test client."""
    return ClickUpClient(mock_config)


@pytest.mark.asyncio
async def test_client_context_manager(mock_config):
    """Test client async context manager."""
    async with ClickUpClient(mock_config) as client:
        assert client is not None


@pytest.mark.asyncio
async def test_handle_401_response(client):
    """Test handling 401 unauthorized response."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b'{"err": "Unauthorized"}'
    mock_response.json.return_value = {"err": "Unauthorized"}

    with pytest.raises(AuthenticationError):
        client._handle_response(mock_response)


@pytest.mark.asyncio
async def test_handle_403_response(client):
    """Test handling 403 forbidden response."""
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.content = b'{"err": "Forbidden"}'
    mock_response.json.return_value = {"err": "Forbidden"}

    with pytest.raises(AuthorizationError):
        client._handle_response(mock_response)


@pytest.mark.asyncio
async def test_handle_404_response(client):
    """Test handling 404 not found response."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.content = b'{"err": "Not found"}'
    mock_response.json.return_value = {"err": "Not found"}

    with pytest.raises(NotFoundError):
        client._handle_response(mock_response)


@pytest.mark.asyncio
async def test_handle_400_response(client):
    """Test handling 400 bad request response."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.content = b'{"err": "Bad request"}'
    mock_response.json.return_value = {"err": "Bad request"}

    with pytest.raises(ValidationError):
        client._handle_response(mock_response)


@pytest.mark.asyncio
async def test_handle_429_response(client):
    """Test handling 429 rate limit response."""
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.content = b'{"err": "Rate limited"}'
    mock_response.json.return_value = {"err": "Rate limited"}
    mock_response.headers = {"Retry-After": "30"}

    with pytest.raises(RateLimitError) as exc_info:
        client._handle_response(mock_response)
    assert exc_info.value.retry_after == 30


@pytest.mark.asyncio
async def test_handle_500_response(client):
    """Test handling 500 server error response."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.content = b'{"err": "Server error"}'
    mock_response.json.return_value = {"err": "Server error"}

    with pytest.raises(ServerError):
        client._handle_response(mock_response)


@pytest.mark.asyncio
async def test_create_folderless_list(client):
    """Test creating a folderless list."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "list123",
        "name": "Test List",
        "orderindex": 0,
        "task_count": 0,
        "archived": False,
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    lst = await client.create_folderless_list("space123", "Test List")
    assert lst.id == "list123"
    assert lst.name == "Test List"


@pytest.mark.asyncio
async def test_get_team(client):
    """Test getting a specific team."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "team": {
            "id": "team123",
            "name": "Test Team",
            "color": "#ff0000",
            "members": [],
        }
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    team = await client.get_team("team123")
    assert team.id == "team123"
    assert team.name == "Test Team"


@pytest.mark.asyncio
async def test_get_space(client):
    """Test getting a specific space."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "space123",
        "name": "Test Space",
        "private": False,
        "statuses": [],
        "multiple_assignees": True,
        "features": {},
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    space = await client.get_space("space123")
    assert space.id == "space123"
    assert space.name == "Test Space"


@pytest.mark.asyncio
async def test_get_folder(client):
    """Test getting a specific folder."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "folder123",
        "name": "Test Folder",
        "orderindex": 0,
        "override_statuses": False,
        "hidden": False,
        "space": {"id": "space123"},
        "task_count": "5",
        "archived": False,
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    folder = await client.get_folder("folder123")
    assert folder.id == "folder123"
    assert folder.name == "Test Folder"


@pytest.mark.asyncio
async def test_get_folders(client):
    """Test getting folders in a space."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "folders": [
            {
                "id": "folder1",
                "name": "Folder 1",
                "orderindex": 0,
                "override_statuses": False,
                "hidden": False,
                "space": {"id": "space123"},
                "task_count": "3",
                "archived": False,
            },
            {
                "id": "folder2",
                "name": "Folder 2",
                "orderindex": 1,
                "override_statuses": False,
                "hidden": False,
                "space": {"id": "space123"},
                "task_count": "7",
                "archived": False,
            },
        ]
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    folders = await client.get_folders("space123")
    assert len(folders) == 2
    assert folders[0].id == "folder1"
    assert folders[1].name == "Folder 2"


@pytest.mark.asyncio
async def test_get_folderless_lists(client):
    """Test getting folderless lists in a space."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "lists": [
            {
                "id": "list1",
                "name": "List 1",
                "orderindex": 0,
                "task_count": 5,
                "archived": False,
            }
        ]
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    lists = await client.get_folderless_lists("space123")
    assert len(lists) == 1
    assert lists[0].id == "list1"


@pytest.mark.asyncio
async def test_search_tasks(client):
    """Test searching for tasks."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tasks": [
            {
                "id": "task1",
                "name": "Found Task",
                "status": {"status": "open"},
                "assignees": [],
            }
        ]
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    tasks = await client.search_tasks("team123", "Found")
    assert len(tasks) == 1
    assert tasks[0].name == "Found Task"


@pytest.mark.asyncio
async def test_create_comment(client):
    """Test creating a comment on a task."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "comment123",
        "comment": [{"text": "Test comment"}],
        "comment_text": "Test comment",
        "user": {"id": 12345, "username": "testuser", "email": "test@example.com"},
        "date": "2024-01-01T00:00:00Z",
        "resolved": False,
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    comment = await client.create_comment("task123", "Test comment")
    assert comment.id == "comment123"


@pytest.mark.asyncio
async def test_get_task_comments(client):
    """Test getting comments for a task."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "comments": [
            {
                "id": "comment1",
                "comment": [{"text": "First comment"}],
                "comment_text": "First comment",
                "user": {"id": 12345, "username": "testuser", "email": "test@example.com"},
                "date": "2024-01-01T00:00:00Z",
                "resolved": False,
            },
            {
                "id": "comment2",
                "comment": [{"text": "Second comment"}],
                "comment_text": "Second comment",
                "user": {"id": 12345, "username": "testuser", "email": "test@example.com"},
                "date": "2024-01-02T00:00:00Z",
                "resolved": False,
            },
        ]
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    comments = await client.get_task_comments("task123")
    assert len(comments) == 2
    assert comments[0].id == "comment1"


@pytest.mark.asyncio
async def test_validate_auth_success(client):
    """Test successful auth validation."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "user": {
            "id": 12345,
            "username": "testuser",
            "email": "test@example.com",
        }
    }

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    is_valid, message, user = await client.validate_auth()
    assert is_valid is True
    assert user is not None
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_validate_auth_failure(client):
    """Test failed auth validation."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"err": "Unauthorized"}

    client.client = AsyncMock()
    client.client.request.return_value = mock_response

    is_valid, message, user = await client.validate_auth()
    assert is_valid is False
    assert user is None
