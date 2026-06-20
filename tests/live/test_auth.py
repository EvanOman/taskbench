"""Live integration tests for authentication and user operations.

These tests verify that authentication works correctly with the real ClickUp API.
"""

import pytest

from taskbench.core import ClickUpClient, Config


@pytest.mark.live
class TestAuthentication:
    """Test authentication with real ClickUp API."""

    async def test_validate_auth_success(self, live_client: ClickUpClient) -> None:
        """Test that authentication validation works with valid credentials."""
        is_valid, message, user = await live_client.validate_auth()

        assert is_valid is True
        assert "✅" in message
        assert user is not None
        assert user.id is not None
        assert user.username is not None
        assert user.email is not None

    async def test_get_user(self, live_client: ClickUpClient) -> None:
        """Test getting current user information."""
        user = await live_client.get_user()

        assert user is not None
        assert user.id is not None
        assert isinstance(user.id, int)
        assert user.username is not None
        assert len(user.username) > 0
        assert user.email is not None
        assert "@" in user.email

    async def test_invalid_token_fails(self) -> None:
        """Test that an invalid API token fails authentication."""
        config = Config()
        config.set_api_token("invalid_token_12345")

        async with ClickUpClient(config) as client:
            is_valid, message, user = await client.validate_auth()

            assert is_valid is False
            assert "❌" in message
            assert user is None

    async def test_config_has_credentials(self, live_config: Config) -> None:
        """Test that the live config has valid credentials."""
        assert live_config.has_credentials() is True
        assert live_config.get_api_token() is not None

    async def test_headers_contain_authorization(self, live_config: Config) -> None:
        """Test that headers are properly configured for API calls."""
        headers = live_config.get_headers()

        assert "Authorization" in headers
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        assert len(headers["Authorization"]) > 0
