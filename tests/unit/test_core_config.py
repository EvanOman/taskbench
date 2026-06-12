"""Tests for configuration management."""

from pathlib import Path

import pytest

from clickup.core import Config


def test_config_creation(temp_config_dir):
    """Test configuration creation."""
    config = Config(config_path=temp_config_dir / "config.json")
    assert config.config_path.parent == temp_config_dir
    assert config.get("api_token") is None


def test_set_api_token(temp_config_dir):
    """Test setting API token."""
    config = Config(config_path=temp_config_dir / "config.json")
    config.set_api_token("test_token")

    assert config.get_api_token() == "test_token"
    assert config.config.api_token == "test_token"


def test_config_persistence(temp_config_dir):
    """Test configuration persistence."""
    config_path = temp_config_dir / "config.json"

    # Create and save config
    config1 = Config(config_path=config_path)
    config1.set_api_token("test_token")
    config1.set("default_team_id", "123456")

    # Load config again
    config2 = Config(config_path=config_path)
    assert config2.get_api_token() == "test_token"
    assert config2.get("default_team_id") == "123456"


def test_config_headers(temp_config_dir):
    """Test HTTP headers generation."""
    config = Config(config_path=temp_config_dir / "config.json")
    config.set_api_token("test_token")

    headers = config.get_headers()
    assert headers["Authorization"] == "test_token"
    assert headers["Content-Type"] == "application/json"


def test_config_headers_no_token(temp_config_dir, monkeypatch):
    """Test headers generation without token."""
    # Clear all possible token environment variables
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
    monkeypatch.delenv("CLICKUP_TOKEN", raising=False)
    monkeypatch.delenv("CLICKUP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLICKUP_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLICKUP_CLIENT_SECRET", raising=False)

    config = Config(config_path=temp_config_dir / "config.json")

    with pytest.raises(ValueError, match="ClickUp API token not configured"):
        config.get_headers()


def test_set_unknown_key_warns_but_stores(temp_config_dir, capsys):
    """Unknown keys warn to stderr but are still stored (forward compat)."""
    config = Config(config_path=temp_config_dir / "config.json")

    config.set("some_unknown_key", "value")

    captured = capsys.readouterr()
    assert "not a recognised config key" in captured.err
    assert config.get("some_unknown_key") == "value"


def test_default_values(temp_config_dir):
    """Test default configuration values."""
    config = Config(config_path=temp_config_dir / "config.json")

    assert config.get("base_url") == "https://api.clickup.com/api/v2"
    assert config.get("timeout") == 30
    assert config.get("max_retries") == 3
    assert config.get("output_format") == "table"
    assert config.get("colors") is True


def test_config_from_env(temp_config_dir, monkeypatch):
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("CLICKUP_API_TOKEN", "env_token")
    monkeypatch.setenv("CLICKUP_DEFAULT_TEAM_ID", "env_team")

    config = Config(config_path=temp_config_dir / "config.json")
    assert config.get_api_token() == "env_token"
    assert config.get("default_team_id") == "env_team"


def test_config_file_precedence(temp_config_dir, monkeypatch):
    """Test that config file takes precedence over environment."""
    monkeypatch.setenv("CLICKUP_API_TOKEN", "env_token")

    config = Config(config_path=temp_config_dir / "config.json")
    config.set_api_token("file_token")

    assert config.get_api_token() == "file_token"


class TestKeyAliases:
    """Tests for KEY_ALIASES (e.g. default_list -> default_list_id)."""

    def test_set_via_alias_stores_canonical_key(self, temp_config_dir):
        """``config.set('default_list', ...)`` stores as ``default_list_id``."""
        config = Config(config_path=temp_config_dir / "config.json")
        config.set("default_list", "12345")
        assert config.get("default_list_id") == "12345"

    def test_get_via_alias_returns_canonical_value(self, temp_config_dir):
        """``config.get('default_list')`` reads from ``default_list_id``."""
        config = Config(config_path=temp_config_dir / "config.json")
        config.set("default_list_id", "67890")
        assert config.get("default_list") == "67890"

    def test_alias_round_trip(self, temp_config_dir):
        """Set via alias, reload, get via alias."""
        path = temp_config_dir / "config.json"
        config = Config(config_path=path)
        config.set("default_list", "round_trip_id")

        config2 = Config(config_path=path)
        assert config2.get("default_list") == "round_trip_id"
        assert config2.get("default_list_id") == "round_trip_id"

    def test_alias_does_not_trigger_unknown_key_warning(self, temp_config_dir, capsys):
        """Setting via alias should NOT produce the unknown-key warning."""
        config = Config(config_path=temp_config_dir / "config.json")
        config.set("default_list", "no_warning")
        captured = capsys.readouterr()
        assert "not a recognised config key" not in captured.err


class TestClickupConfigPathEnvVar:
    """Tests for CLICKUP_CONFIG_PATH environment variable support."""

    def test_env_var_overrides_default_path(self, tmp_path, monkeypatch):
        """Config() with no args uses CLICKUP_CONFIG_PATH when set."""
        custom_path = tmp_path / "custom" / "config.json"
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(custom_path))

        config = Config()
        assert config.config_path == custom_path

    def test_env_var_creates_parent_dirs_on_save(self, tmp_path, monkeypatch):
        """Saving config creates parent directories for the env-var path."""
        custom_path = tmp_path / "deep" / "nested" / "config.json"
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(custom_path))

        config = Config()
        config.set_api_token("tok_from_env_path")
        assert custom_path.exists()

        # Reload and verify persistence
        config2 = Config()
        assert config2.get_api_token() == "tok_from_env_path"

    def test_explicit_config_path_wins_over_env_var(self, tmp_path, monkeypatch):
        """An explicit config_path argument takes precedence over the env var."""
        env_path = tmp_path / "env" / "config.json"
        explicit_path = tmp_path / "explicit" / "config.json"
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(env_path))

        config = Config(config_path=explicit_path)
        assert config.config_path == explicit_path

    def test_env_var_not_set_falls_back_to_default(self, monkeypatch):
        """Without CLICKUP_CONFIG_PATH, Config() uses the default path."""
        monkeypatch.delenv("CLICKUP_CONFIG_PATH", raising=False)
        # The autouse fixture already patches _get_default_config_path to a
        # tmpdir, so just verify we get a path under the patched location
        # (not None or an error).
        config = Config()
        assert config.config_path is not None
        assert isinstance(config.config_path, Path)
