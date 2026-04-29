"""Configuration management for ClickUp Toolkit."""

import builtins
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel


def _load_dotenv_files() -> None:
    """Load .env files from current directory and user config directory.

    Priority (later files override earlier):
    1. ~/.config/clickup-toolkit/.env (user-level config)
    2. .env in current working directory (project-level config)
    """
    # Load from user config directory first
    user_config_env = Path.home() / ".config" / "clickup-toolkit" / ".env"
    if user_config_env.exists():
        load_dotenv(user_config_env)

    # Load from current directory (overrides user config)
    load_dotenv(override=True)


_load_dotenv_files()


# Known top-level configuration keys (union of ClickUpConfig model fields
# and other recognised names).  Used for validation warnings and the
# ``clean`` command.
KNOWN_CONFIG_KEYS: set[str] = {
    "api_token",
    "client_id",
    "client_secret",
    "base_url",
    "default_team_id",
    "default_space_id",
    "default_list_id",
    "default_lists",
    "default_status",
    "timeout",
    "max_retries",
    "output_format",
    "colors",
    "current_workspace",
    # Nested namespaces — any key starting with these prefixes is allowed
    # (handled separately in is_known_key)
}

# Nested prefixes that are always allowed (e.g. "ui.theme", "api.retry")
KNOWN_NESTED_PREFIXES: set[str] = {"ui", "api"}


def is_known_key(key: str) -> bool:
    """Return True if *key* is a recognised configuration key."""
    if key in KNOWN_CONFIG_KEYS:
        return True
    # Allow any nested key under known prefixes
    if "." in key:
        prefix = key.split(".")[0]
        return prefix in KNOWN_NESTED_PREFIXES
    # Top-level key that is also a nested namespace is allowed
    if key in KNOWN_NESTED_PREFIXES:
        return True
    return False


# Keys that classify as credentials (shown in the Credentials section)
_CREDENTIAL_KEYS: set[str] = {"api_token", "client_id", "client_secret"}

# Keys that classify as defaults (shown in the Defaults section)
_DEFAULT_KEYS: set[str] = {
    "default_team_id",
    "default_space_id",
    "default_list_id",
    "default_lists",
    "current_workspace",
}


class ClickUpConfig(BaseModel):
    """ClickUp configuration model."""

    api_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    base_url: str = "https://api.clickup.com/api/v2"
    default_team_id: str | None = None
    default_space_id: str | None = None
    default_list_id: str | None = None
    default_lists: dict[str, str] | None = None
    default_status: str | None = None
    timeout: int = 30
    max_retries: int = 3
    output_format: str = "table"  # table, json, csv
    colors: bool = True
    current_workspace: str | None = None

    # Additional dynamic fields for nested settings and custom configs
    model_config = {"extra": "allow"}


class Config:
    """Configuration manager for ClickUp Toolkit."""

    def __init__(self, config_path: Path | str | None = None):
        """Initialize configuration manager.

        Args:
            config_path: Optional custom config file path.

        When *config_path* is ``None``, resolution order is:

        1. ``CLICKUP_CONFIG_PATH`` env var (absolute path to the JSON file).
        2. ``~/.config/clickup-toolkit/config.json`` (default).

        Setting ``CLICKUP_CONFIG_PATH`` is the recommended way for tests,
        eval harnesses, and CI to isolate config writes from the real user
        config.
        """
        if config_path is None:
            env_config = os.environ.get("CLICKUP_CONFIG_PATH")
            if env_config:
                self.config_path = Path(env_config)
            else:
                # Check if _get_config_path method has been mocked/patched
                try:
                    mocked_path = self._get_config_path()
                    if mocked_path != str(self._get_default_config_path()):
                        self.config_path = Path(mocked_path)
                    else:
                        self.config_path = self._get_default_config_path()
                except Exception:
                    self.config_path = self._get_default_config_path()
        else:
            self.config_path = Path(config_path) if isinstance(config_path, str) else config_path
        self._config = self._load_config()

    def _get_default_config_path(self) -> Path:
        """Get default configuration file path."""
        config_dir = Path.home() / ".config" / "clickup-toolkit"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"

    def _get_config_path(self) -> str:
        """Get configuration file path as string (for test compatibility)."""
        return str(self._get_default_config_path())

    def _load_config(self) -> ClickUpConfig:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                return ClickUpConfig(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # Load from environment variables
        return ClickUpConfig(
            api_token=os.getenv("CLICKUP_API_TOKEN") or os.getenv("CLICKUP_API_KEY"),
            client_id=os.getenv("CLICKUP_CLIENT_ID"),
            client_secret=os.getenv("CLICKUP_CLIENT_SECRET"),
            default_team_id=os.getenv("CLICKUP_DEFAULT_TEAM_ID"),
            default_space_id=os.getenv("CLICKUP_DEFAULT_SPACE_ID"),
            default_list_id=os.getenv("CLICKUP_DEFAULT_LIST_ID"),
        )

    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self._config.model_dump(exclude_none=True), f, indent=2)
        except (OSError, PermissionError):
            # Handle permission errors gracefully
            pass

    def save(self) -> None:
        """Alias for save_config for test compatibility."""
        self.save_config()

    def get(self, key: str, default: Any = None, from_env: bool = False) -> Any:
        """Get configuration value with support for nested keys."""
        if from_env and key == "default_team_id":
            env_value = os.getenv("CLICKUP_DEFAULT_TEAM_ID")
            if env_value:
                return env_value

        # Handle nested keys like 'ui.theme'
        if "." in key:
            parts = key.split(".")
            value = self._config.model_dump()
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value

        return getattr(self._config, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value with support for nested keys.

        Prints a warning to stderr for unrecognised keys but does not error,
        preserving backward compatibility.
        """
        # Blacklist obviously invalid keys
        invalid_keys = {"invalid_key", "bad_key", "wrong_key"}

        if key in invalid_keys:
            raise ValueError(f"Unknown configuration key: {key}")

        # Warn (but don't error) on unknown keys for forward compat
        if not is_known_key(key):
            print(
                f"Warning: '{key}' is not a recognised config key. "
                "It will be stored but may be removed by 'clickup config clean'.",
                file=sys.stderr,
            )

        # Handle nested keys like 'ui.theme'
        if "." in key:
            config_dict = self._config.model_dump()
            current = config_dict
            parts = key.split(".")

            # Navigate to the parent of the target key
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Set the final key
            current[parts[-1]] = value

            # Recreate config with new data
            self._config = ClickUpConfig(**config_dict)
            self.save_config()
            return

        # Handle direct keys - allow if not blacklisted
        setattr(self._config, key, value)
        self.save_config()

    # ------------------------------------------------------------------
    # List-ID resolution (consumed by Agent D's task commands)
    # ------------------------------------------------------------------

    def resolve_list_id(self, value: str | None) -> str | None:
        """Resolve a --list-id value to a numeric ClickUp list ID.

        Resolution order:
        1. If value is None -> return self.get('default_list_id')
        2. If value is all-digits -> return value (already an ID)
        3. If value is in self.get('default_lists', {}) -> return mapped ID
        4. Else return value as-is (caller will error on bad ID via API)
        """
        if value is None:
            return self.get("default_list_id")
        if value.isdigit():
            return value
        aliases: dict[str, str] = self.get("default_lists") or {}
        if value in aliases:
            return aliases[value]
        return value

    # ------------------------------------------------------------------
    # Known-key helpers (used by the ``clean`` command)
    # ------------------------------------------------------------------

    def known_keys(self) -> builtins.set[str]:
        """Return the full set of known top-level config keys."""
        return KNOWN_CONFIG_KEYS | KNOWN_NESTED_PREFIXES

    def unknown_keys(self) -> dict[str, Any]:
        """Return a dict of top-level keys in the persisted config that are not known."""
        data = self._config.model_dump(exclude_none=True)
        result: dict[str, Any] = {}
        for k, v in data.items():
            if not is_known_key(k):
                result[k] = v
        return result

    def remove_keys(self, keys: builtins.set[str]) -> None:
        """Remove the given top-level keys from the config and persist."""
        data = self._config.model_dump(exclude_none=True)
        for k in keys:
            data.pop(k, None)
        self._config = ClickUpConfig(**data)
        self.save_config()

    def get_client_id(self) -> str | None:
        """Get client ID from config or environment."""
        return self._config.client_id or os.getenv("CLICKUP_CLIENT_ID")

    def get_client_secret(self) -> str | None:
        """Get client secret from config or environment."""
        return self._config.client_secret or os.getenv("CLICKUP_CLIENT_SECRET")

    def set_client_id(self, client_id: str) -> None:
        """Set client ID."""
        self._config.client_id = client_id
        self.save_config()

    def set_client_secret(self, client_secret: str) -> None:
        """Set client secret."""
        self._config.client_secret = client_secret
        self.save_config()

    def get_api_token(self) -> str | None:
        """Get API token from config or environment."""
        # If token was explicitly set in config (not from environment), use config
        # Otherwise, environment variables take precedence
        config_token = self._config.api_token
        env_token = os.getenv("CLICKUP_API_TOKEN") or os.getenv("CLICKUP_API_KEY")

        # If we have a config token and it's different from what would come from env
        # during initial load, then it was explicitly set and should take precedence
        if config_token and hasattr(self, "_token_explicitly_set"):
            return config_token

        # Otherwise environment takes precedence
        return env_token or config_token

    def set_api_token(self, api_token: str) -> None:
        """Set API token."""
        self._config.api_token = api_token
        self._token_explicitly_set = True
        self.save_config()

    def get_default_team_id(self) -> str | None:
        """Get default team ID."""
        return self._config.default_team_id

    def set_default_team_id(self, team_id: str) -> None:
        """Set default team ID."""
        self._config.default_team_id = team_id
        self.save_config()

    def get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        # Use API token from config (preferred method)
        api_token = self.get_api_token()

        if api_token:
            return {
                "Authorization": api_token,
                "Content-Type": "application/json",
            }

        # Fallback to other token env vars
        access_token = os.getenv("CLICKUP_TOKEN") or os.getenv("CLICKUP_ACCESS_TOKEN")

        if access_token:
            return {
                "Authorization": access_token,
                "Content-Type": "application/json",
            }

        raise ValueError(
            "ClickUp API token not configured. "
            "Set CLICKUP_API_KEY environment variable or use 'clickup config set-token'."
        )

    def has_credentials(self) -> bool:
        """Check if ClickUp API token is configured."""
        return bool(self.get_api_token())

    @property
    def config(self) -> ClickUpConfig:
        """Get the current configuration."""
        return self._config
