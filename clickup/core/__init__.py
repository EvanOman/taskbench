"""ClickUp Toolkit Core - Shared ClickUp API client and utilities."""

__version__ = "0.1.0"

from .client import ClickUpClient
from .config import Config
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClickUpError,
    ConfigurationError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    ResourceAccessError,
    ServerError,
    ValidationError,
)
from .models import Comment, Folder, List, Space, Task, Team, User, Workspace
from .providers import TaskProvider, get_provider, provider_name, provider_requires_credentials

__all__ = [
    "ClickUpClient",
    "TaskProvider",
    "Task",
    "Workspace",
    "List",
    "User",
    "Team",
    "Space",
    "Folder",
    "Comment",
    "Config",
    "get_provider",
    "provider_name",
    "provider_requires_credentials",
    "ClickUpError",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceAccessError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "NetworkError",
    "RequestTimeoutError",
    "ConfigurationError",
    "ValidationError",
]
