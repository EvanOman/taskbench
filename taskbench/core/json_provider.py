"""Local JSON task provider used for agent research and offline testing."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from rich.console import Console

from .config import Config
from .exceptions import NotFoundError, ValidationError
from .models import Comment, Folder, Space, Task, Team, User
from .models import List as ClickUpList


def default_store_path() -> Path:
    """Default JSON store path for the local provider."""
    return Path.home() / ".config" / "taskbench" / "mock-store.json"


def _now_ms() -> str:
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def seed_store() -> dict[str, Any]:
    """Return a deterministic mock workspace."""
    now = _now_ms()
    statuses = [
        {"status": "to do", "type": "open", "color": "#87909f", "orderindex": 0},
        {"status": "in progress", "type": "custom", "color": "#2f80ed", "orderindex": 1},
        {"status": "on-deck", "type": "custom", "color": "#f2c94c", "orderindex": 2},
        {"status": "complete", "type": "closed", "color": "#27ae60", "orderindex": 3},
    ]
    return {
        "next_task": 1006,
        "next_comment": 5002,
        "user": {"id": 1, "username": "Mock Agent", "email": "agent@example.test"},
        "teams": [
            {
                "id": "team_mock",
                "name": "Mock Workspace",
                "color": "#2f80ed",
                "members": [{"user": {"id": 1, "username": "Mock Agent", "email": "agent@example.test"}}],
            }
        ],
        "spaces": [
            {
                "id": "space_ops",
                "name": "Operations",
                "private": False,
                "multiple_assignees": True,
                "features": {},
                "statuses": statuses,
                "team_id": "team_mock",
            }
        ],
        "folders": [
            {
                "id": "folder_daily",
                "name": "Daily Work",
                "orderindex": 0,
                "override_statuses": False,
                "hidden": False,
                "space": {"id": "space_ops", "name": "Operations"},
                "task_count": "5",
                "lists": [],
            }
        ],
        "lists": [
            {
                "id": "list_inbox",
                "name": "Inbox",
                "folder_id": "folder_daily",
                "space": {"id": "space_ops", "name": "Operations"},
                "folder": {"id": "folder_daily", "name": "Daily Work"},
                "statuses": statuses,
                "task_count": 3,
            },
            {
                "id": "list_active",
                "name": "Active",
                "folder_id": "folder_daily",
                "space": {"id": "space_ops", "name": "Operations"},
                "folder": {"id": "folder_daily", "name": "Daily Work"},
                "statuses": statuses,
                "task_count": 2,
            },
        ],
        "tasks": [
            {
                "id": "mock_1001",
                "name": "Draft weekly project update",
                "description": "Summarize completed work, blockers, and next actions.",
                "status": statuses[0],
                "date_created": now,
                "date_updated": now,
                "archived": False,
                "assignees": [],
                "priority": {"id": "2", "priority": "2"},
                "list": {"id": "list_inbox", "name": "Inbox"},
                "url": "mock://task/mock_1001",
            },
            {
                "id": "mock_1002",
                "name": "Triage customer feedback notes",
                "description": "Group feedback into bugs, feature requests, and follow-ups.",
                "status": statuses[1],
                "date_created": now,
                "date_updated": now,
                "archived": False,
                "assignees": [],
                "priority": {"id": "3", "priority": "3"},
                "list": {"id": "list_active", "name": "Active"},
                "url": "mock://task/mock_1002",
            },
            {
                "id": "mock_1003",
                "name": "Prepare invoice packet",
                "description": "Collect receipts and confirm totals.",
                "status": statuses[2],
                "date_created": now,
                "date_updated": now,
                "archived": False,
                "assignees": [],
                "priority": {"id": "4", "priority": "4"},
                "list": {"id": "list_inbox", "name": "Inbox"},
                "url": "mock://task/mock_1003",
            },
            {
                "id": "mock_1004",
                "name": "Follow up on API docs review",
                "description": "Ask for final comments and close the loop.",
                "status": statuses[1],
                "date_created": now,
                "date_updated": now,
                "archived": False,
                "assignees": [],
                "priority": {"id": "2", "priority": "2"},
                "list": {"id": "list_active", "name": "Active"},
                "url": "mock://task/mock_1004",
            },
            {
                "id": "mock_1005",
                "name": "Clean up stale to-do labels",
                "description": "Find labels that no longer match the current workflow.",
                "status": statuses[0],
                "date_created": now,
                "date_updated": now,
                "archived": False,
                "assignees": [],
                "priority": None,
                "list": {"id": "list_inbox", "name": "Inbox"},
                "url": "mock://task/mock_1005",
            },
        ],
        "comments": {
            "mock_1001": [
                {
                    "id": "comment_5001",
                    "comment": [],
                    "comment_text": "Use concise bullets.",
                    "user": {"id": 1, "username": "Mock Agent", "email": "agent@example.test"},
                    "date": now,
                    "resolved": False,
                }
            ]
        },
    }


def write_seed_store(path: Path, *, force: bool = False) -> None:
    """Create a seed store on disk."""
    if path.exists() and not force:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seed_store(), indent=2), encoding="utf-8")


class JsonProvider:
    """Provider adapter backed by a local JSON file."""

    def __init__(self, config: Config | None = None, console: Console | None = None):
        self.config = config or Config()
        self.console = console or Console()
        configured = os.getenv("CLICKUP_JSON_STORE") or self.config.get("json_store_path")
        self.path = Path(configured).expanduser() if configured else default_store_path()

    async def __aenter__(self) -> Self:
        self._ensure_store()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def _ensure_store(self) -> None:
        if not self.path.exists():
            write_seed_store(self.path)

    def _load(self) -> dict[str, Any]:
        self._ensure_store()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, store: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(store, indent=2), encoding="utf-8")

    def _list_data(self, store: dict[str, Any], list_id: str) -> dict[str, Any]:
        for list_data in store.get("lists", []):
            if list_data["id"] == list_id:
                return list_data
        raise NotFoundError(f"List not found: {list_id}")

    def _task_data(self, store: dict[str, Any], task_id: str) -> dict[str, Any]:
        for task in store.get("tasks", []):
            if task["id"] == task_id:
                return task
        raise NotFoundError(f"Task not found: {task_id}")

    def _task_model(self, task: dict[str, Any], store: dict[str, Any] | None = None) -> Task:
        """Materialise a Task model, annotating ``comment_count`` from the store.

        The real ClickUp API doesn't return comment counts on task objects, so
        this is a local-provider enrichment — it spares audit-style flows the
        N+1 `task comments list` round-trips (issue #29 / Agent 06).
        """
        data = deepcopy(task)
        if store is not None:
            data["comment_count"] = len(store.get("comments", {}).get(task["id"], []))
        return Task(**data)

    def _folder_model(self, folder: dict[str, Any], store: dict[str, Any]) -> Folder:
        """Materialise a Folder model, enriching child lists and task_count at read time.

        Stored ``task_count`` / ``lists`` values are ignored — both are
        recomputed from the current store so reads always reflect the latest
        state.  This mirrors the ``_task_model`` comment_count enrichment
        pattern (commit 1ebe042).
        """
        data = deepcopy(folder)
        folder_id = data["id"]
        child_lists = [lst for lst in store.get("lists", []) if lst.get("folder_id") == folder_id]
        data["lists"] = child_lists
        total_tasks = sum(
            len([t for t in store.get("tasks", []) if t.get("list", {}).get("id") == lst["id"]]) for lst in child_lists
        )
        data["task_count"] = str(total_tasks)
        return Folder(**data)

    def _resolve_status(
        self, list_data: dict[str, Any], name: str, store: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Look up a status by name on the given list, falling back to its space.

        Returns the full status object (with color/type/orderindex) so updates
        echo the same shape as `task statuses`. Raises ``ValidationError`` if
        the name is unknown — matching what the real ClickUp API does for
        invalid statuses, so the local provider doesn't silently swallow typos.

        When ``store`` is provided, the space-level fallback uses it directly
        instead of re-reading from disk.
        """
        for status in list_data.get("statuses") or []:
            if status.get("status", "").lower() == name.lower():
                return deepcopy(status)
        space = list_data.get("space") or {}
        if store is None:
            store = self._load()
        space_statuses: list[dict[str, Any]] = []
        for space_data in store.get("spaces", []):
            if space_data.get("id") == space.get("id"):
                space_statuses = space_data.get("statuses") or []
                for status in space_statuses:
                    if status.get("status", "").lower() == name.lower():
                        return deepcopy(status)
                break
        # Surface the names actually visible at *either* level so the error is
        # actionable even when the list inherits its statuses from the space.
        known: list[str] = []
        for status in list_data.get("statuses") or space_statuses:
            value = status.get("status")
            if isinstance(value, str) and value:
                known.append(value)
        raise ValidationError(f"Unknown status '{name}'. Available: {', '.join(known) or '(none)'}.")

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        method = method.upper()
        endpoint = "/" + endpoint.strip("/")
        store = self._load()
        if method == "GET" and endpoint == "/team":
            return {"teams": store.get("teams", [])}
        if method == "GET" and endpoint.startswith("/list/") and endpoint.endswith("/task"):
            list_id = endpoint.split("/")[2]
            params = kwargs.get("params") or {}
            return {"tasks": [task.model_dump(mode="json") for task in await self.get_tasks(list_id, **params)]}
        if method == "GET" and endpoint.startswith("/list/"):
            return deepcopy(self._list_data(store, endpoint.split("/")[2]))
        if method == "GET" and endpoint.startswith("/task/"):
            return deepcopy(self._task_data(store, endpoint.split("/")[2]))
        raise ValidationError(f"Unsupported local raw request: {method} {endpoint}")

    async def get_user(self) -> User:
        return User(**self._load()["user"])

    async def validate_auth(self) -> tuple[bool, str, User | None]:
        user = await self.get_user()
        return True, f"Local JSON provider active ({user.username}, {user.email})", user

    async def get_teams(self) -> list[Team]:
        return [Team(**team) for team in self._load().get("teams", [])]

    async def get_team(self, team_id: str) -> Team:
        for team in self._load().get("teams", []):
            if team["id"] == team_id:
                return Team(**team)
        raise NotFoundError(f"Workspace not found: {team_id}")

    async def get_team_members(self, team_id: str) -> list[User]:
        team = await self.get_team(team_id)
        return [member.user for member in team.members]

    async def get_spaces(self, team_id: str) -> list[Space]:
        return [Space(**space) for space in self._load().get("spaces", []) if space.get("team_id") == team_id]

    async def get_space(self, space_id: str) -> Space:
        for space in self._load().get("spaces", []):
            if space["id"] == space_id:
                return Space(**space)
        raise NotFoundError(f"Space not found: {space_id}")

    async def get_folders(self, space_id: str) -> list[Folder]:
        store = self._load()
        return [
            self._folder_model(folder, store)
            for folder in store.get("folders", [])
            if folder.get("space", {}).get("id") == space_id
        ]

    async def get_folder(self, folder_id: str) -> Folder:
        store = self._load()
        for folder in store.get("folders", []):
            if folder["id"] == folder_id:
                return self._folder_model(folder, store)
        raise NotFoundError(f"Folder not found: {folder_id}")

    async def create_folder(self, space_id: str, name: str, **kwargs: Any) -> Folder:
        store = self._load()
        space = next((item for item in store.get("spaces", []) if item["id"] == space_id), None)
        if space is None:
            raise NotFoundError(f"Space not found: {space_id}")
        folder_id = f"folder_{len(store.get('folders', [])) + 1}"
        folder: dict[str, Any] = {
            "id": folder_id,
            "name": name,
            "orderindex": len(store.get("folders", [])),
            "override_statuses": False,
            "hidden": False,
            "space": {"id": space_id, "name": space["name"]},
            "task_count": "0",
            "lists": [],
            **kwargs,
        }
        store.setdefault("folders", []).append(folder)
        self._save(store)
        return self._folder_model(folder, store)

    async def get_lists(self, folder_id: str) -> list[ClickUpList]:
        return [ClickUpList(**item) for item in self._load().get("lists", []) if item.get("folder_id") == folder_id]

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]:
        return [
            ClickUpList(**item)
            for item in self._load().get("lists", [])
            if item.get("space", {}).get("id") == space_id and not item.get("folder_id")
        ]

    async def get_list(self, list_id: str) -> ClickUpList:
        return ClickUpList(**self._list_data(self._load(), list_id))

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList:
        store = self._load()
        folder = next((item for item in store.get("folders", []) if item["id"] == folder_id), None)
        if folder is None:
            raise NotFoundError(f"Folder not found: {folder_id}")
        list_id = f"list_{len(store.get('lists', [])) + 1}"
        item: dict[str, Any] = {
            "id": list_id,
            "name": name,
            "folder_id": folder_id,
            "folder": {"id": folder_id, "name": folder["name"]},
            "space": folder["space"],
            "task_count": 0,
            **kwargs,
        }
        store.setdefault("lists", []).append(item)
        self._save(store)
        return ClickUpList(**item)

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList:
        store = self._load()
        space = next((item for item in store.get("spaces", []) if item["id"] == space_id), None)
        if space is None:
            raise NotFoundError(f"Space not found: {space_id}")
        list_id = f"list_{len(store.get('lists', [])) + 1}"
        item: dict[str, Any] = {
            "id": list_id,
            "name": name,
            "space": {"id": space_id, "name": space["name"]},
            "task_count": 0,
            **kwargs,
        }
        store.setdefault("lists", []).append(item)
        self._save(store)
        return ClickUpList(**item)

    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]:
        store = self._load()
        self._list_data(store, list_id)
        tasks = [task for task in store.get("tasks", []) if task.get("list", {}).get("id") == list_id]
        statuses = filters.get("statuses")
        if statuses:
            wanted = {str(status).lower() for status in statuses}
            tasks = [task for task in tasks if (task.get("status") or {}).get("status", "").lower() in wanted]
        if filters.get("include_closed") is False:
            tasks = [task for task in tasks if (task.get("status") or {}).get("type") != "closed"]
        for filter_key, field, op in (
            ("date_created_gt", "date_created", "gt"),
            ("date_created_lt", "date_created", "lt"),
            ("date_updated_gt", "date_updated", "gt"),
            ("date_updated_lt", "date_updated", "lt"),
        ):
            if filter_key in filters:
                threshold = int(filters[filter_key])
                if op == "gt":
                    tasks = [task for task in tasks if int(task.get(field) or 0) > threshold]
                else:
                    tasks = [task for task in tasks if int(task.get(field) or 0) < threshold]
        return [self._task_model(task, store) for task in tasks]

    async def get_task(self, task_id: str) -> Task:
        store = self._load()
        return self._task_model(self._task_data(store, task_id), store)

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task:
        store = self._load()
        list_data = self._list_data(store, list_id)
        task_id = f"mock_{store.get('next_task', 1000)}"
        store["next_task"] = store.get("next_task", 1000) + 1
        status = kwargs.pop("status", "to do")
        priority = kwargs.pop("priority", None)
        now = _now_ms()
        task = {
            "id": task_id,
            "name": name,
            "description": kwargs.pop("description", None),
            "status": self._resolve_status(list_data, status, store) if isinstance(status, str) else status,
            "date_created": now,
            "date_updated": now,
            "archived": False,
            "assignees": [],
            "priority": {"id": str(priority), "priority": str(priority)} if priority is not None else None,
            "list": {"id": list_id, "name": list_data["name"]},
            "url": f"mock://task/{task_id}",
            **kwargs,
        }
        store.setdefault("tasks", []).append(task)
        list_data["task_count"] = int(list_data.get("task_count") or 0) + 1
        self._save(store)
        return self._task_model(task, store)

    async def update_task(self, task_id: str, **updates: Any) -> Task:
        store = self._load()
        task = self._task_data(store, task_id)
        list_data = self._list_data(store, task.get("list", {}).get("id", ""))
        for key, value in updates.items():
            if key == "status" and isinstance(value, str):
                task[key] = self._resolve_status(list_data, value, store)
            elif key == "priority" and value is not None:
                task[key] = {"id": str(value), "priority": str(value)}
            else:
                task[key] = value
        task["date_updated"] = _now_ms()
        self._save(store)
        return self._task_model(task, store)

    async def delete_task(self, task_id: str) -> bool:
        store = self._load()
        original = len(store.get("tasks", []))
        store["tasks"] = [task for task in store.get("tasks", []) if task["id"] != task_id]
        if len(store["tasks"]) == original:
            raise NotFoundError(f"Task not found: {task_id}")
        self._save(store)
        return True

    async def get_task_comments(self, task_id: str) -> list[Comment]:
        store = self._load()
        self._task_data(store, task_id)
        return [Comment(**comment) for comment in store.get("comments", {}).get(task_id, [])]

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment:
        store = self._load()
        self._task_data(store, task_id)
        comment_id = f"comment_{store.get('next_comment', 5000)}"
        store["next_comment"] = store.get("next_comment", 5000) + 1
        comment: dict[str, Any] = {
            "id": comment_id,
            "comment": [],
            "comment_text": comment_text,
            "user": store["user"],
            "date": _now_ms(),
            "resolved": False,
            **kwargs,
        }
        store.setdefault("comments", {}).setdefault(task_id, []).append(comment)
        self._save(store)
        return Comment(**comment)

    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]:
        _ = filters
        store = self._load()
        if not any(team["id"] == team_id for team in store.get("teams", [])):
            raise NotFoundError(f"Workspace not found: {team_id}")
        needle = query.lower()
        tasks = [
            task
            for task in store.get("tasks", [])
            if needle in task.get("name", "").lower() or needle in (task.get("description") or "").lower()
        ]
        return [self._task_model(task, store) for task in tasks]
