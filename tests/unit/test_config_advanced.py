"""Advanced tests for configuration functionality."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from taskbench.core.config import Config


@pytest.fixture
def temp_config_file():
    """Create temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_data = {"default_team_id": "team123", "default_list_id": "list123", "api_token": "test_token_123"}
        json.dump(config_data, f)
        f.flush()
        yield f.name
    os.unlink(f.name)


def test_config_file_loading(temp_config_file):
    """Test loading configuration from file."""
    with patch.object(Config, "_get_config_path", return_value=temp_config_file):
        config = Config()
        assert config.get("default_team_id") == "team123"
        assert config.get("default_list_id") == "list123"
        assert config.get("api_token") == "test_token_123"


def test_config_environment_override():
    """Test environment variables override config file."""
    with (
        patch.dict(os.environ, {"CLICKUP_API_TOKEN": "env_token", "CLICKUP_DEFAULT_TEAM_ID": "env_team"}),
        tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f,
    ):
        # Create a fresh config file for this test
        json.dump({}, f)
        f.flush()

        with patch.object(Config, "_get_config_path", return_value=f.name):
            config = Config()
            assert config.get_api_token() == "env_token"
            assert config.get("default_team_id", from_env=True) == "env_team"

        os.unlink(f.name)


def test_config_save_and_reload(temp_config_file):
    """Test saving and reloading configuration."""
    with patch.object(Config, "_get_config_path", return_value=temp_config_file):
        config = Config()
        config.set("new_setting", "new_value")
        config.save()

        # Create new instance to test reload
        config2 = Config()
        assert config2.get("new_setting") == "new_value"
        assert config2.get("default_team_id") == "team123"  # Original values preserved


def test_config_default_values():
    """Test default configuration values."""
    with patch.object(Config, "_load_config", return_value={}):
        config = Config()
        assert config.get("nonexistent_key") is None
        assert config.get("nonexistent_key", default="default_val") == "default_val"


def test_config_credential_validation():
    """Test credential validation."""
    config = Config()

    # Test with no credentials
    with patch.object(config, "get_api_token", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            assert not config.has_credentials()

    # Test with API token
    with patch.object(config, "get_api_token", return_value="test_token"):
        assert config.has_credentials()


def test_config_workspace_management():
    """Test workspace/team configuration."""
    config = Config()

    # Test setting default workspace
    config.set_default_team_id("team456")
    assert config.get_default_team_id() == "team456"

    # Test workspace switching
    config.set("current_workspace", "workspace789")
    assert config.get("current_workspace") == "workspace789"


def test_config_api_token_management():
    """Test API token configuration."""
    config = Config()

    # Test setting API token
    config.set_api_token("new_token_123")
    assert config.get_api_token() == "new_token_123"

    # Test token priority (config over environment)
    with patch.dict(os.environ, {"CLICKUP_API_TOKEN": "env_token"}):
        # Config token should take precedence
        assert config.get_api_token() == "new_token_123"


def test_config_file_creation():
    """Test config file is created if it doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = os.path.join(temp_dir, "nonexistent_config.json")

        with patch.object(Config, "_get_config_path", return_value=config_path):
            config = Config()
            config.set("test_key", "test_value")
            config.save()

            assert os.path.exists(config_path)

            # Verify content
            with open(config_path) as f:
                data = json.load(f)
                assert data["test_key"] == "test_value"


def test_config_error_handling():
    """Test configuration error handling."""
    # Test invalid JSON file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("invalid json content")
        f.flush()

        with patch.object(Config, "_get_config_path", return_value=f.name):
            # Should handle invalid JSON gracefully
            config = Config()
            assert config.get("any_key") is None

        os.unlink(f.name)


def test_config_permission_handling():
    """Test handling of file permission errors."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        f.flush()

        # Make file read-only
        os.chmod(f.name, 0o444)

        try:
            with patch.object(Config, "_get_config_path", return_value=f.name):
                config = Config()
                config.set("test_key", "test_value")
                # Should handle permission error gracefully when saving
                config.save()  # This might fail, but shouldn't crash
        finally:
            # Restore permissions for cleanup
            os.chmod(f.name, 0o644)
            os.unlink(f.name)


def test_config_nested_settings():
    """Test nested configuration settings."""
    config = Config()

    # Test setting nested values
    config.set("ui.theme", "dark")
    config.set("ui.pagination", 20)
    config.set("api.retry_count", 3)

    assert config.get("ui.theme") == "dark"
    assert config.get("ui.pagination") == 20
    assert config.get("api.retry_count") == 3


def test_config_list_and_dict_values():
    """Test storing lists and dictionaries in config."""
    config = Config()

    # Test list values
    config.set("favorite_lists", ["list1", "list2", "list3"])
    assert config.get("favorite_lists") == ["list1", "list2", "list3"]

    # Test dict values
    config.set("workspace_aliases", {"dev": "team123", "prod": "team456"})
    aliases = config.get("workspace_aliases")
    assert aliases["dev"] == "team123"
    assert aliases["prod"] == "team456"


def test_config_migration():
    """Test configuration migration/upgrade scenarios."""
    # Test loading old config format and upgrading
    old_config = {
        "clickup_api_key": "old_key_format",  # Old field name
        "team_id": "team123",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(old_config, f)
        f.flush()

        with patch.object(Config, "_get_config_path", return_value=f.name):
            config = Config()
            # Should handle migration gracefully
            # Implementation would depend on actual migration logic
            assert config.get("team_id") == "team123"

        os.unlink(f.name)
