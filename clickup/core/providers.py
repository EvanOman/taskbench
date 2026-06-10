"""Provider port and adapter factory for task backends."""

from __future__ import annotations

import os
from typing import Any, Protocol, Self

from rich.console import Console

from .client import ClickUpClient
from .config import Config
from .json_provider import JsonProvider
from .models import Comment, Folder, Space, Task, Team, User
from .models import List as ClickUpList


class TaskProvider(Protocol):
    """Port consumed by the CLI; adapters implement this interface."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]: ...

    async def get_user(self) -> User: ...

    async def validate_auth(self) -> tuple[bool, str, User | None]: ...

    async def get_teams(self) -> list[Team]: ...

    async def get_team(self, team_id: str) -> Team: ...

    async def get_team_members(self, team_id: str) -> list[User]: ...

    async def get_spaces(self, team_id: str) -> list[Space]: ...

    async def get_space(self, space_id: str) -> Space: ...

    async def get_folders(self, space_id: str) -> list[Folder]: ...

    async def get_folder(self, folder_id: str) -> Folder: ...

    async def create_folder(self, space_id: str, name: str, **kwargs: Any) -> Folder: ...

    async def get_lists(self, folder_id: str) -> list[ClickUpList]: ...

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]: ...

    async def get_list(self, list_id: str) -> ClickUpList: ...

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList: ...

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList: ...

    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]: ...

    async def get_task(self, task_id: str) -> Task: ...

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task: ...

    async def update_task(self, task_id: str, **updates: Any) -> Task: ...

    async def delete_task(self, task_id: str) -> bool: ...

    async def get_task_comments(self, task_id: str) -> list[Comment]: ...

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment: ...

    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]: ...


def provider_name(config: Config) -> str:
    """Return the configured provider name."""
    return (os.getenv("CLICKUP_PROVIDER") or config.get("provider") or "clickup").strip().lower()


def provider_requires_credentials(config: Config) -> bool:
    """Whether the selected provider needs ClickUp credentials."""
    return provider_name(config) == "clickup"


def get_provider(config: Config | None = None, console: Console | None = None) -> TaskProvider:
    """Build the selected provider adapter."""
    config = config or Config()
    name = provider_name(config)
    if name in {"json", "local", "mock"}:
        return JsonProvider(config, console)
    if name == "clickup":
        return ClickUpClient(config, console)
    raise ValueError(f"Unknown provider '{name}'. Use 'clickup' or 'json'.")
