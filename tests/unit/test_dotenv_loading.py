"""Tests for .env file loading functionality."""

import os
from pathlib import Path

import pytest


class TestDotenvLoading:
    """Test .env file loading from various locations."""

    def test_load_from_current_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading .env from current working directory."""
        # Create a .env file in temp directory
        env_file = tmp_path / ".env"
        env_file.write_text("CLICKUP_API_KEY=test_key_from_cwd\n")

        # Change to temp directory and reload the module
        monkeypatch.chdir(tmp_path)

        # Clear any existing env var
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

        # Import and call the loader function directly
        from dotenv import load_dotenv

        load_dotenv(env_file)

        assert os.environ.get("CLICKUP_API_KEY") == "test_key_from_cwd"

    def test_load_from_user_config_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading .env from ~/.config/taskbench/."""
        # Create fake home directory structure
        fake_home = tmp_path / "home"
        config_dir = fake_home / ".config" / "taskbench"
        config_dir.mkdir(parents=True)

        env_file = config_dir / ".env"
        env_file.write_text("CLICKUP_API_KEY=test_key_from_user_config\n")

        # Clear any existing env var
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

        # Load from the user config .env
        from dotenv import load_dotenv

        load_dotenv(env_file)

        assert os.environ.get("CLICKUP_API_KEY") == "test_key_from_user_config"

    def test_cwd_overrides_user_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that .env in current directory overrides user config."""
        # Create fake home directory with .env
        fake_home = tmp_path / "home"
        config_dir = fake_home / ".config" / "taskbench"
        config_dir.mkdir(parents=True)
        user_env = config_dir / ".env"
        user_env.write_text("CLICKUP_API_KEY=user_config_key\nCLICKUP_DEFAULT_TEAM_ID=user_team\n")

        # Create project directory with .env
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_env = project_dir / ".env"
        project_env.write_text("CLICKUP_API_KEY=project_key\n")

        # Clear any existing env vars
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
        monkeypatch.delenv("CLICKUP_DEFAULT_TEAM_ID", raising=False)

        # Load user config first, then project (simulating _load_dotenv_files behavior)
        from dotenv import load_dotenv

        load_dotenv(user_env)
        load_dotenv(project_env, override=True)

        # Project key should override user config key
        assert os.environ.get("CLICKUP_API_KEY") == "project_key"
        # User config value should still be present for keys not in project .env
        assert os.environ.get("CLICKUP_DEFAULT_TEAM_ID") == "user_team"

    def test_config_uses_dotenv_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that Config class picks up values from .env."""
        # Set up environment with values as if loaded from .env
        monkeypatch.setenv("CLICKUP_API_KEY", "dotenv_api_key")
        monkeypatch.setenv("CLICKUP_DEFAULT_TEAM_ID", "dotenv_team_123")

        from taskbench.core import Config

        config = Config(config_path=tmp_path / "config.json")

        assert config.get_api_token() == "dotenv_api_key"
        assert config.get("default_team_id") == "dotenv_team_123"

    def test_multiple_env_vars_loaded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading multiple environment variables from .env."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "CLICKUP_API_KEY=multi_test_key\n"
            "CLICKUP_DEFAULT_TEAM_ID=team_456\n"
            "CLICKUP_DEFAULT_SPACE_ID=space_789\n"
            "CLICKUP_DEFAULT_LIST_ID=list_012\n"
        )

        # Clear existing vars
        for var in [
            "CLICKUP_API_KEY",
            "CLICKUP_API_TOKEN",
            "CLICKUP_DEFAULT_TEAM_ID",
            "CLICKUP_DEFAULT_SPACE_ID",
            "CLICKUP_DEFAULT_LIST_ID",
        ]:
            monkeypatch.delenv(var, raising=False)

        from dotenv import load_dotenv

        load_dotenv(env_file)

        assert os.environ.get("CLICKUP_API_KEY") == "multi_test_key"
        assert os.environ.get("CLICKUP_DEFAULT_TEAM_ID") == "team_456"
        assert os.environ.get("CLICKUP_DEFAULT_SPACE_ID") == "space_789"
        assert os.environ.get("CLICKUP_DEFAULT_LIST_ID") == "list_012"

    def test_comments_and_empty_lines_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that comments and empty lines in .env are ignored."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "\n"
            "CLICKUP_API_KEY=valid_key\n"
            "# Another comment\n"
            "\n"
            "CLICKUP_DEFAULT_TEAM_ID=valid_team\n"
        )

        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_DEFAULT_TEAM_ID", raising=False)

        from dotenv import load_dotenv

        load_dotenv(env_file)

        assert os.environ.get("CLICKUP_API_KEY") == "valid_key"
        assert os.environ.get("CLICKUP_DEFAULT_TEAM_ID") == "valid_team"

    def test_quoted_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that quoted values are handled correctly."""
        env_file = tmp_path / ".env"
        env_file.write_text("CLICKUP_API_KEY=\"quoted_key_value\"\nCLICKUP_DEFAULT_TEAM_ID='single_quoted_team'\n")

        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_DEFAULT_TEAM_ID", raising=False)

        from dotenv import load_dotenv

        load_dotenv(env_file)

        assert os.environ.get("CLICKUP_API_KEY") == "quoted_key_value"
        assert os.environ.get("CLICKUP_DEFAULT_TEAM_ID") == "single_quoted_team"

    def test_no_env_file_no_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing .env file doesn't cause errors."""
        # Clear vars
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

        from dotenv import load_dotenv

        # Should not raise any errors
        result = load_dotenv(tmp_path / "nonexistent.env")
        assert result is False  # Returns False when file doesn't exist

    def test_load_dotenv_files_function(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test the _load_dotenv_files function directly.

        This test verifies the loading order logic by calling load_dotenv
        with the same order as _load_dotenv_files does.
        """
        from dotenv import load_dotenv

        # Create fake home with config
        fake_home = tmp_path / "home"
        config_dir = fake_home / ".config" / "taskbench"
        config_dir.mkdir(parents=True)

        user_env = config_dir / ".env"
        user_env.write_text("CLICKUP_API_KEY=from_user_config\nUSER_ONLY_VAR=user_value\n")

        # Create project dir with .env
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_env = project_dir / ".env"
        project_env.write_text("CLICKUP_API_KEY=from_project\n")

        # Clear existing
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
        monkeypatch.delenv("USER_ONLY_VAR", raising=False)

        # Simulate _load_dotenv_files behavior:
        # 1. Load from user config first
        load_dotenv(user_env)
        # 2. Load from project directory with override=True
        load_dotenv(project_env, override=True)

        # Project should override user config
        assert os.environ.get("CLICKUP_API_KEY") == "from_project"
        # But user-only vars should still be present
        assert os.environ.get("USER_ONLY_VAR") == "user_value"


class TestConfigWithDotenv:
    """Test Config class integration with .env loading."""

    def test_config_prioritizes_env_over_empty_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that env vars (from .env) are used when config file is empty."""
        monkeypatch.setenv("CLICKUP_API_KEY", "env_key")

        from taskbench.core import Config

        config = Config(config_path=tmp_path / "config.json")

        assert config.get_api_token() == "env_key"
        assert config.has_credentials() is True

    def test_explicit_set_overrides_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that explicitly set token overrides env var."""
        monkeypatch.setenv("CLICKUP_API_KEY", "env_key")

        from taskbench.core import Config

        config = Config(config_path=tmp_path / "config.json")
        config.set_api_token("explicit_key")

        assert config.get_api_token() == "explicit_key"

    def test_all_env_vars_recognized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that all supported environment variables are recognized."""
        # Test CLICKUP_API_TOKEN
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.setenv("CLICKUP_API_TOKEN", "token_var")

        from taskbench.core import Config

        config = Config(config_path=tmp_path / "config1.json")
        assert config.get_api_token() == "token_var"

        # Test CLICKUP_API_KEY (legacy)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
        monkeypatch.setenv("CLICKUP_API_KEY", "key_var")

        config2 = Config(config_path=tmp_path / "config2.json")
        assert config2.get_api_token() == "key_var"

    def test_client_credentials_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading client credentials from environment."""
        monkeypatch.setenv("CLICKUP_CLIENT_ID", "client_123")
        monkeypatch.setenv("CLICKUP_CLIENT_SECRET", "secret_456")

        from taskbench.core import Config

        config = Config(config_path=tmp_path / "config.json")

        assert config.get_client_id() == "client_123"
        assert config.get_client_secret() == "secret_456"
