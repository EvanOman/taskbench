"""Tests for ClickUp API client."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from taskbench.core import (
    AuthenticationError,
    ClickUpClient,
    ClickUpError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    ResourceAccessError,
    ValidationError,
)


@pytest.mark.asyncio
async def test_client_initialization(mock_config):
    """Test client initialization."""
    client = ClickUpClient(mock_config)
    assert client.config == mock_config
    assert client.client is not None


@pytest.mark.asyncio
async def test_successful_request(mock_clickup_client):
    """Test successful API request."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"tasks": [{"id": "task123", "name": "Test Task"}]}

    mock_clickup_client.client.request.return_value = mock_response

    result = await mock_clickup_client._request("GET", "/test")
    assert result["tasks"][0]["id"] == "task123"


@pytest.mark.asyncio
async def test_authentication_error(mock_clickup_client):
    """Test authentication error handling."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b"Unauthorized"

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(AuthenticationError):
        await mock_clickup_client._request("GET", "/test")


@pytest.mark.asyncio
async def test_not_found_error(mock_clickup_client):
    """Test 404 error handling."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.content = b"Not Found"

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(NotFoundError) as exc:
        await mock_clickup_client._request("GET", "/task/86aj0p7b2")
    assert "/task/86aj0p7b2" in str(exc.value)


@pytest.mark.asyncio
async def test_validation_error(mock_clickup_client):
    """Test validation error handling."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"err": "Invalid request"}
    mock_response.content = b'{"err": "Invalid request"}'

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(ValidationError) as exc_info:
        await mock_clickup_client._request("GET", "/test")

    assert "Invalid request" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rate_limit_error(mock_clickup_client):
    """Test rate limit error handling."""
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    mock_response.content = b"Rate limited"

    mock_clickup_client.client.request.return_value = mock_response

    # Set max_retries to 0 to avoid sleeping during the test
    mock_clickup_client.config.set("max_retries", 0)

    with pytest.raises(RateLimitError) as exc_info:
        await mock_clickup_client._request("GET", "/test")

    assert exc_info.value.retry_after == 60


@pytest.mark.asyncio
async def test_get_task(mock_clickup_client, sample_task):
    """Test getting a single task."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample_task.model_dump()

    mock_clickup_client.client.request.return_value = mock_response

    task = await mock_clickup_client.get_task("task123")
    assert task.id == "task123"
    assert task.name == "Test Task"


@pytest.mark.asyncio
async def test_get_tasks(mock_clickup_client, sample_task):
    """Test getting multiple tasks."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"tasks": [sample_task.model_dump(), sample_task.model_dump()]}

    mock_clickup_client.client.request.return_value = mock_response

    tasks = await mock_clickup_client.get_tasks("list123")
    assert len(tasks) == 2
    assert all(task.id == "task123" for task in tasks)


@pytest.mark.asyncio
async def test_create_task(mock_clickup_client, sample_task):
    """Test creating a task."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample_task.model_dump()

    mock_clickup_client.client.request.return_value = mock_response

    task = await mock_clickup_client.create_task("list123", "New Task")
    assert task.name == "Test Task"  # From sample_task

    # Verify the request was made correctly
    mock_clickup_client.client.request.assert_called_once()
    call_args = mock_clickup_client.client.request.call_args
    assert call_args[0][0] == "POST"  # HTTP method
    assert "/list/list123/task" in call_args[0][1]  # URL


@pytest.mark.asyncio
async def test_update_task(mock_clickup_client, sample_task):
    """Test updating a task."""
    updated_task = sample_task.model_copy()
    updated_task.name = "Updated Task"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = updated_task.model_dump()

    mock_clickup_client.client.request.return_value = mock_response

    task = await mock_clickup_client.update_task("task123", name="Updated Task")
    assert task.name == "Updated Task"


@pytest.mark.asyncio
async def test_delete_task(mock_clickup_client):
    """Test deleting a task."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    mock_clickup_client.client.request.return_value = mock_response

    result = await mock_clickup_client.delete_task("task123")
    assert result is True


@pytest.mark.asyncio
async def test_raw_request_reuses_request_path(mock_clickup_client):
    """Raw API escape hatch delegates through the normal request helper."""
    with patch.object(mock_clickup_client, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"ok": True}

        result = await mock_clickup_client.raw_request("get", "/task/task123", params={"foo": "bar"})

    assert result == {"ok": True}
    mock_request.assert_awaited_once_with("GET", "/task/task123", params={"foo": "bar"})


@pytest.mark.asyncio
async def test_get_teams(mock_clickup_client, sample_team):
    """Test getting teams."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"teams": [sample_team.model_dump()]}

    mock_clickup_client.client.request.return_value = mock_response

    teams = await mock_clickup_client.get_teams()
    assert len(teams) == 1
    assert teams[0].id == "team123"


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_network_error_retry(mock_sleep, mock_clickup_client):
    """Test network error retry logic."""
    # First call fails, second succeeds
    mock_clickup_client.client.request.side_effect = [
        httpx.ConnectError("Connection failed"),
        Mock(status_code=200, json=lambda: {"success": True}),
    ]

    result = await mock_clickup_client._request("GET", "/test")
    assert result["success"] is True
    assert mock_clickup_client.client.request.call_count == 2
    # Verify sleep was called with exponential backoff (2^0 = 1)
    mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_max_retries_exceeded(mock_sleep, mock_clickup_client):
    """Test max retries exceeded."""
    mock_clickup_client.client.request.side_effect = httpx.ConnectError("Connection failed")

    with pytest.raises(ClickUpError, match="Network error"):
        await mock_clickup_client._request("GET", "/test")

    # Should retry max_retries + 1 times
    assert mock_clickup_client.client.request.call_count == 4  # 3 retries + 1 initial
    # Verify exponential backoff: 2^0, 2^1, 2^2 = 1, 2, 4
    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(1)  # 2^0
    mock_sleep.assert_any_call(2)  # 2^1
    mock_sleep.assert_any_call(4)  # 2^2


@pytest.mark.asyncio
async def test_context_manager(mock_config):
    """Test client as async context manager."""
    async with ClickUpClient(mock_config) as client:
        assert client is not None

    # Client should be closed after context


@pytest.mark.asyncio
async def test_validate_auth_success(mock_clickup_client, sample_user):
    """Test successful auth validation."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"user": sample_user.model_dump()}

    mock_clickup_client.client.request.return_value = mock_response

    is_valid, message, user = await mock_clickup_client.validate_auth()

    assert is_valid is True
    assert "Authentication valid" in message
    assert user is not None
    assert user.username == sample_user.username


@pytest.mark.asyncio
async def test_validate_auth_invalid_token(mock_clickup_client):
    """Test auth validation with invalid token."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b"Unauthorized"

    mock_clickup_client.client.request.return_value = mock_response

    is_valid, message, user = await mock_clickup_client.validate_auth()

    assert is_valid is False
    assert "Invalid API token" in message
    assert user is None


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_validate_auth_network_error(mock_sleep, mock_clickup_client):
    """Test auth validation with network error."""
    mock_clickup_client.client.request.side_effect = httpx.ConnectError("Connection failed")

    is_valid, message, user = await mock_clickup_client.validate_auth()

    assert is_valid is False
    assert "Network error" in message
    assert user is None


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_timeout_raises_request_timeout_error(mock_sleep, mock_clickup_client):
    """httpx.TimeoutException should raise RequestTimeoutError, not NetworkError."""
    mock_clickup_client.client.request.side_effect = httpx.ReadTimeout("read timed out")

    with pytest.raises(RequestTimeoutError) as exc_info:
        await mock_clickup_client._request("GET", "/test")

    assert "timed out" in str(exc_info.value).lower()
    assert "timeout" in str(exc_info.value).lower()
    # Verify the class name is usable for CLI error rendering (type(e).__name__)
    assert type(exc_info.value).__name__ == "RequestTimeoutError"


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_connect_error_still_raises_network_error(mock_sleep, mock_clickup_client):
    """httpx.ConnectError should still raise NetworkError (not RequestTimeoutError)."""
    mock_clickup_client.client.request.side_effect = httpx.ConnectError("refused")

    with pytest.raises(NetworkError):
        await mock_clickup_client._request("GET", "/test")


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_timeout_retries_then_raises(mock_sleep, mock_clickup_client):
    """TimeoutException should be retried before raising RequestTimeoutError."""
    mock_clickup_client.client.request.side_effect = httpx.ReadTimeout("timeout")

    with pytest.raises(RequestTimeoutError):
        await mock_clickup_client._request("GET", "/test")

    # 1 initial + 3 retries = 4 attempts
    assert mock_clickup_client.client.request.call_count == 4
    assert mock_sleep.call_count == 3


@pytest.mark.asyncio
async def test_401_on_resource_endpoint_raises_resource_access_error(mock_clickup_client):
    """ClickUp returns 401 for unknown resource IDs; must raise ResourceAccessError."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b'{"err": "Team not authorized"}'
    mock_response.json.return_value = {"err": "Team not authorized"}

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(ResourceAccessError) as exc:
        await mock_clickup_client._request("GET", "/task/doesnotexist123")
    msg = str(exc.value)
    assert "Team not authorized" in msg
    assert "401 for /task/doesnotexist123" in msg
    assert "the ID does not exist" in msg


@pytest.mark.asyncio
async def test_401_on_user_endpoint_stays_authentication_error(mock_clickup_client):
    """401 on /user (non-resource endpoint) must stay AuthenticationError."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b'{"err": "Unauthorized"}'
    mock_response.json.return_value = {"err": "Unauthorized"}

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(AuthenticationError):
        await mock_clickup_client._request("GET", "/user")


@pytest.mark.asyncio
async def test_create_comment_handles_minimal_response(mock_clickup_client):
    """ClickUp's create-comment endpoint returns only {id, hist_id, date}."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"{}"
    mock_response.json.return_value = {"id": 458, "hist_id": "abc123", "date": 1568036964079}

    mock_clickup_client.client.request.return_value = mock_response

    comment = await mock_clickup_client.create_comment("task123", "status: looking into it")
    assert comment.id == "458"
    assert comment.comment_text == "status: looking into it"
    assert comment.user is None
    assert comment.date == "1568036964079"
