"""ClickUp API client implementation."""

import asyncio
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from rich.console import Console

from .config import Config
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClickUpError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    ResourceAccessError,
    ServerError,
    ValidationError,
)
from .models import Comment, Folder, Space, Task, Team, User
from .models import List as ClickUpList


class ClickUpClient:
    """ClickUp API client with comprehensive error handling and rate limiting."""

    def __init__(self, config: Config | None = None, console: Console | None = None):
        """Initialize ClickUp client.

        Args:
            config: Configuration instance
            console: Rich console for output
        """
        self.config = config or Config()
        self.console = console or Console()
        self.client = httpx.AsyncClient(timeout=self.config.get("timeout", 30), headers=self.config.get_headers())

    async def __aenter__(self) -> "ClickUpClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.client.aclose()

    # Endpoints that target a specific resource (as opposed to auth-only
    # endpoints like /user or the bare /team root).  When ClickUp returns
    # 401 on one of these, the most likely cause is a bad resource ID, not
    # a bad token — so we raise ResourceAccessError instead of
    # AuthenticationError.
    _RESOURCE_ENDPOINT_RE = re.compile(
        r"^/(?:task|list|folder|space|view)/[^/]"  # /task/<id>, /list/<id>/task, etc.
        r"|^/team/\d+/.+"  # /team/123/space, /team/123/task, …
    )

    def _handle_response(self, response: httpx.Response, *, endpoint: str = "") -> dict[str, Any]:
        """Handle HTTP response and raise appropriate exceptions."""
        try:
            if response.status_code in (200, 201):
                result: dict[str, Any] = response.json()
                return result
            elif response.status_code == 204:
                # No Content (e.g., successful DELETE) — return empty dict
                return {}
            elif response.status_code == 401:
                try:
                    error_data = response.json() if response.content else {}
                except (json.JSONDecodeError, ValueError):
                    error_data = {}
                detail = error_data.get("err", "") if isinstance(error_data, dict) else ""
                if self._RESOURCE_ENDPOINT_RE.search(endpoint):
                    message = (
                        f"ClickUp returned 401 for {endpoint}"
                        f"{': ' + detail if detail else ''}. "
                        "For resource endpoints this usually means the ID does not exist "
                        "or is not accessible to this token; it can also mean the token "
                        "itself is invalid — if other commands work, double-check the ID."
                    )
                    raise ResourceAccessError(message, response.status_code)
                message = (
                    f"ClickUp rejected the request (401{': ' + detail if detail else ''}). "
                    "This usually means an invalid API token. "
                    "If other commands work, double-check the ID."
                )
                raise AuthenticationError(message, response.status_code)
            elif response.status_code == 403:
                raise AuthorizationError(
                    f"Insufficient permissions: {endpoint}" if endpoint else "Insufficient permissions",
                    response.status_code,
                )
            elif response.status_code == 404:
                raise NotFoundError(
                    f"Resource not found: {endpoint}" if endpoint else "Resource not found",
                    response.status_code,
                )
            elif response.status_code == 400:
                error_data = response.json() if response.content else {}
                raise ValidationError(error_data.get("err", "Bad request"), response.status_code, error_data)
            elif response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError("Rate limit exceeded", retry_after=retry_after, status_code=response.status_code)
            elif response.status_code >= 500:
                raise ServerError(f"Server error: {response.status_code}", response.status_code)
            else:
                raise ClickUpError(f"Unexpected status code: {response.status_code}", response.status_code)
        except json.JSONDecodeError as e:
            raise ClickUpError(f"Invalid JSON response: {response.text}", response.status_code) from e

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make HTTP request with retry logic."""
        # Preserve the original endpoint (with leading /) for error messages
        # before normalising it for URL construction.
        raw_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        base_url = self.config.get("base_url")
        # Ensure base_url ends with / and endpoint starts without /
        if not base_url.endswith("/"):
            base_url += "/"
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
        url = urljoin(base_url, endpoint)
        max_retries = self.config.get("max_retries", 3)

        for attempt in range(max_retries + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                return self._handle_response(response, endpoint=raw_endpoint)
            except RateLimitError as e:
                if attempt < max_retries:
                    await asyncio.sleep(e.retry_after or 60)
                    continue
                raise
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)  # Exponential backoff
                    continue
                raise RequestTimeoutError(
                    f"Request timed out: {e}. "
                    "Consider retrying or increasing the timeout with 'taskbench config set timeout <seconds>'."
                ) from e
            except httpx.ConnectError as e:
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)  # Exponential backoff
                    continue
                raise NetworkError(f"Network error: {str(e)}") from e

        raise ClickUpError("Max retries exceeded")

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated raw ClickUp API request.

        This is the supported escape hatch for endpoints the typed client does
        not wrap yet. It intentionally reuses the normal request path so auth,
        base URL handling, retries, and error mapping stay consistent.
        """
        return await self._request(method.upper(), endpoint, **kwargs)

    # Teams/Workspaces
    async def get_teams(self) -> list[Team]:
        """Get all teams for the authenticated user."""
        data = await self._request("GET", "/team")
        return [Team(**team) for team in data.get("teams", [])]

    async def get_team(self, team_id: str) -> Team:
        """Get team details."""
        data = await self._request("GET", f"/team/{team_id}")
        return Team(**data["team"])

    # Spaces
    async def get_spaces(self, team_id: str) -> list[Space]:
        """Get all spaces for a team."""
        data = await self._request("GET", f"/team/{team_id}/space")
        return [Space(**space) for space in data.get("spaces", [])]

    async def get_space(self, space_id: str) -> Space:
        """Get space details."""
        data = await self._request("GET", f"/space/{space_id}")
        return Space(**data)

    # Folders
    async def get_folders(self, space_id: str) -> list[Folder]:
        """Get all folders in a space."""
        data = await self._request("GET", f"/space/{space_id}/folder")
        return [Folder(**folder) for folder in data.get("folders", [])]

    async def get_folder(self, folder_id: str) -> Folder:
        """Get folder details."""
        data = await self._request("GET", f"/folder/{folder_id}")
        return Folder(**data)

    async def create_folder(self, space_id: str, name: str, **kwargs: Any) -> Folder:
        """Create a new folder in a space."""
        payload = {"name": name, **kwargs}
        data = await self._request("POST", f"/space/{space_id}/folder", json=payload)
        return Folder(**data)

    # Lists
    async def get_lists(self, folder_id: str) -> list[ClickUpList]:
        """Get all lists in a folder."""
        data = await self._request("GET", f"/folder/{folder_id}/list")
        return [ClickUpList(**list_data) for list_data in data.get("lists", [])]

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]:
        """Get all folderless lists in a space."""
        data = await self._request("GET", f"/space/{space_id}/list")
        return [ClickUpList(**list_data) for list_data in data.get("lists", [])]

    async def get_list(self, list_id: str) -> ClickUpList:
        """Get list details."""
        data = await self._request("GET", f"/list/{list_id}")
        return ClickUpList(**data)

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList:
        """Create a new list in a folder."""
        payload = {"name": name, **kwargs}
        data = await self._request("POST", f"/folder/{folder_id}/list", json=payload)
        return ClickUpList(**data)

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList:
        """Create a new folderless list in a space."""
        payload = {"name": name, **kwargs}
        data = await self._request("POST", f"/space/{space_id}/list", json=payload)
        return ClickUpList(**data)

    # Tasks
    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]:
        """Get all tasks in a list."""
        params = {k: v for k, v in filters.items() if v is not None}
        data = await self._request("GET", f"/list/{list_id}/task", params=params)
        return [Task(**task) for task in data.get("tasks", [])]

    async def get_task(self, task_id: str) -> Task:
        """Get task details."""
        data = await self._request("GET", f"/task/{task_id}")
        return Task(**data)

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task:
        """Create a new task."""
        payload = {"name": name, **kwargs}
        data = await self._request("POST", f"/list/{list_id}/task", json=payload)
        return Task(**data)

    async def update_task(self, task_id: str, **updates: Any) -> Task:
        """Update a task."""
        data = await self._request("PUT", f"/task/{task_id}", json=updates)
        return Task(**data)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        await self._request("DELETE", f"/task/{task_id}")
        return True

    # Users
    async def get_user(self) -> User:
        """Get current user information."""
        data = await self._request("GET", "/user")
        return User(**data["user"])

    async def validate_auth(self) -> tuple[bool, str, User | None]:
        """Validate authentication and return user info.

        Returns:
            Tuple of (is_valid, message, user_info)
        """
        try:
            user = await self.get_user()
            return True, f"✅ Authentication valid for {user.username} ({user.email})", user
        except AuthenticationError:
            return False, "❌ Invalid API token", None
        except AuthorizationError:
            return False, "❌ API token lacks required permissions", None
        except NetworkError as e:
            return False, f"❌ Network error: {str(e)}", None
        except ClickUpError as e:
            return False, f"❌ API error: {str(e)}", None

    async def get_team_members(self, team_id: str) -> list[User]:
        """Get team members.

        Uses GET /team/{team_id} and extracts members from the team object,
        since ClickUp v2 API does not have a dedicated /team/{id}/member endpoint.
        """
        team = await self.get_team(team_id)
        return [member.user for member in team.members]

    # Comments
    async def get_task_comments(self, task_id: str) -> list[Comment]:
        """Get comments for a task."""
        data = await self._request("GET", f"/task/{task_id}/comment")
        return [Comment(**comment) for comment in data.get("comments", [])]

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment:
        """Create a comment on a task.

        ClickUp's create endpoint returns only ``{id, hist_id, date}``; the
        rest of the Comment is synthesized from the request payload.
        """
        payload = {"comment_text": comment_text, **kwargs}
        data = await self._request("POST", f"/task/{task_id}/comment", json=payload)
        return Comment(
            id=str(data.get("id", "")),
            comment=[{"text": comment_text}],
            comment_text=comment_text,
            date=str(data.get("date", "")),
        )

    # Search
    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]:
        """Search for tasks across the team."""
        params = {"query": query, **filters}
        data = await self._request("GET", f"/team/{team_id}/task", params=params)
        return [Task(**task) for task in data.get("tasks", [])]
