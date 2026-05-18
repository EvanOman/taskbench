"""Plane task provider -- maps the Plane REST API to the TaskProvider protocol.

Mapping:
    Team        -> Workspace
    Space       -> synthetic single Space wrapping the workspace
    Folder      -> no-op (returns [] and stable placeholder)
    List        -> Plane Project
    Task        -> Plane Work Item (issue)
    Status      -> Plane Workflow State
    Comment     -> Plane Work-Item Comment
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Self

import httpx
from rich.console import Console

from .config import Config
from .exceptions import NotFoundError
from .models import Comment, Folder, Space, Task, Team, User
from .models import List as ClickUpList


def _now_ms() -> str:
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def _iso_to_ms(iso: str | None) -> str | None:
    """Convert an ISO-8601 timestamp to epoch milliseconds."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except (ValueError, TypeError):
        return None


# Plane priority -> ClickUp-style priority id mapping
_PLANE_PRIORITY_TO_ID: dict[str, str] = {
    "urgent": "1",
    "high": "2",
    "medium": "3",
    "low": "4",
    "none": "4",
}

# Reverse: ClickUp priority id -> Plane priority name
_ID_TO_PLANE_PRIORITY: dict[str, str] = {
    "1": "urgent",
    "2": "high",
    "3": "medium",
    "4": "low",
}

# Plane state group -> ClickUp-style status type
_GROUP_TO_TYPE: dict[str, str] = {
    "backlog": "open",
    "unstarted": "open",
    "started": "custom",
    "completed": "closed",
    "cancelled": "closed",
    "triage": "open",
}


class PlaneProvider:
    """TaskProvider adapter backed by a self-hosted Plane instance."""

    def __init__(self, config: Config | None = None, console: Console | None = None) -> None:
        self.config = config or Config()
        self.console = console or Console()

        self.base_url = (os.getenv("PLANE_URL") or self.config.get("plane_url") or "http://localhost:18930").rstrip("/")

        self.token = os.getenv("PLANE_TOKEN") or self.config.get("plane_token") or ""

        self.workspace_slug = os.getenv("PLANE_WORKSPACE") or self.config.get("plane_workspace") or "taskflow"

        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1/workspaces/{self.workspace_slug}",
            headers={
                "X-API-Key": self.token,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PlaneProvider must be used as an async context manager")
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, data: dict) -> dict[str, Any]:
        r = await self._http.post(path, json=data)
        r.raise_for_status()
        return r.json()

    async def _patch(self, path: str, data: dict) -> dict[str, Any]:
        r = await self._http.patch(path, json=data)
        r.raise_for_status()
        return r.json()

    async def _delete(self, path: str) -> None:
        r = await self._http.delete(path)
        r.raise_for_status()

    async def _paginate_results(self, path: str, params: dict | None = None) -> list[dict]:
        """Fetch all pages of a paginated Plane response."""
        all_results: list[dict] = []
        params = dict(params or {})
        params.setdefault("per_page", "100")
        while True:
            data = await self._get(path, params=params)
            all_results.extend(data.get("results", []))
            if not data.get("next_page_results", False):
                break
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break
            params["cursor"] = next_cursor
        return all_results

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    async def _get_states(self, project_id: str) -> list[dict]:
        return await self._paginate_results(f"/projects/{project_id}/states/")

    async def _state_by_id(self, project_id: str, state_id: str) -> dict | None:
        states = await self._get_states(project_id)
        for s in states:
            if s["id"] == state_id:
                return s
        return None

    async def _state_by_name(self, project_id: str, name: str) -> dict | None:
        states = await self._get_states(project_id)
        for s in states:
            if s["name"].lower() == name.lower():
                return s
        return None

    # ------------------------------------------------------------------
    # Model conversions
    # ------------------------------------------------------------------

    def _workspace_id(self) -> str:
        """Stable synthetic ID for the workspace."""
        return f"ws_{self.workspace_slug}"

    def _space_id(self) -> str:
        """Stable synthetic Space ID."""
        return f"sp_{self.workspace_slug}"

    def _folder_id(self) -> str:
        """Stable synthetic Folder ID."""
        return f"fld_{self.workspace_slug}"

    def _to_team(self) -> Team:
        return Team(
            id=self._workspace_id(),
            name=self.workspace_slug,
            color="#2f80ed",
            members=[],
        )

    def _to_space(self) -> Space:
        return Space(
            id=self._space_id(),
            name=self.workspace_slug,
            private=False,
            multiple_assignees=True,
            features={},
            statuses=[],
        )

    def _project_to_list(self, project: dict) -> ClickUpList:
        return ClickUpList(
            id=project["id"],
            name=project.get("name", ""),
            space={"id": self._space_id(), "name": self.workspace_slug},
            folder={"id": self._folder_id(), "name": "Projects"},
        )

    def _to_status_info(self, state: dict | None) -> dict:
        if not state:
            return {"status": "unknown", "type": "open", "color": "#87909f"}
        group = state.get("group", "unstarted")
        return {
            "status": state.get("name", "unknown"),
            "type": _GROUP_TO_TYPE.get(group, "custom"),
            "color": state.get("color", "#87909f"),
            "orderindex": state.get("sequence", 0),
        }

    def _work_item_to_task(
        self,
        wi: dict,
        project_id: str,
        project_name: str = "",
        state: dict | None = None,
    ) -> Task:
        priority_name = wi.get("priority") or "none"
        pri_id = _PLANE_PRIORITY_TO_ID.get(priority_name, "3")

        status_info = self._to_status_info(state)

        return Task(
            id=wi["id"],
            name=wi.get("name", ""),
            description=wi.get("description_stripped") or wi.get("description") or "",
            status=status_info,
            date_created=_iso_to_ms(wi.get("created_at")),
            date_updated=_iso_to_ms(wi.get("updated_at")),
            archived=False,
            assignees=[],
            priority={"id": pri_id, "priority": pri_id} if pri_id else None,
            list={"id": project_id, "name": project_name},
            url=f"{self.base_url}/{self.workspace_slug}/projects/{project_id}/work-items/{wi['id']}",
        )

    def _to_comment(self, c: dict) -> Comment:
        actor = c.get("actor")
        if isinstance(actor, dict):
            user = User(
                id=actor.get("id", 0) if isinstance(actor.get("id"), int) else 0,
                username=actor.get("display_name") or actor.get("first_name") or "Unknown",
                email=actor.get("email") or "",
            )
        else:
            # actor may be a UUID string or None
            user = User(id=0, username="Unknown", email="")

        return Comment(
            id=c.get("id", ""),
            comment=[],
            comment_text=_strip_html(c.get("comment_html", "")),
            user=user,
            date=_iso_to_ms(c.get("created_at")) or _now_ms(),
            resolved=False,
        )

    def _to_user(self) -> User:
        return User(
            id=1,
            username="Plane Admin",
            email="plane-admin@local.dev",
        )

    # ------------------------------------------------------------------
    # TaskProvider interface
    # ------------------------------------------------------------------

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        method = method.upper()
        r = await self._http.request(method, endpoint, **kwargs)
        r.raise_for_status()
        return r.json()

    async def get_user(self) -> User:
        return self._to_user()

    async def validate_auth(self) -> tuple[bool, str, User | None]:
        try:
            # Quick smoke test: list projects
            await self._get("/projects/", params={"per_page": "1"})
            user = self._to_user()
            return True, f"Plane provider active ({self.workspace_slug})", user
        except Exception as e:
            return False, f"Plane auth failed: {e}", None

    async def get_teams(self) -> list[Team]:
        return [self._to_team()]

    async def get_team(self, team_id: str) -> Team:
        return self._to_team()

    async def get_team_members(self, team_id: str) -> list[User]:
        return [self._to_user()]

    async def get_spaces(self, team_id: str) -> list[Space]:
        return [self._to_space()]

    async def get_space(self, space_id: str) -> Space:
        return self._to_space()

    async def get_folders(self, space_id: str) -> list[Folder]:
        return [
            Folder(
                id=self._folder_id(),
                name="Projects",
                orderindex=0,
                override_statuses=False,
                hidden=False,
                space={"id": self._space_id(), "name": self.workspace_slug},
                task_count="0",
            )
        ]

    async def get_folder(self, folder_id: str) -> Folder:
        return Folder(
            id=self._folder_id(),
            name="Projects",
            orderindex=0,
            override_statuses=False,
            hidden=False,
            space={"id": self._space_id(), "name": self.workspace_slug},
            task_count="0",
        )

    async def get_lists(self, folder_id: str) -> list[ClickUpList]:
        projects = await self._paginate_results("/projects/")
        return [self._project_to_list(p) for p in projects]

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]:
        # All projects exposed as folderless lists too
        projects = await self._paginate_results("/projects/")
        return [self._project_to_list(p) for p in projects]

    async def get_list(self, list_id: str) -> ClickUpList:
        data = await self._get(f"/projects/{list_id}/")
        return self._project_to_list(data)

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList:
        identifier = name[:5].upper().replace(" ", "")
        data = await self._post(
            "/projects/",
            {
                "name": name,
                "identifier": identifier,
                "description": kwargs.get("content", ""),
            },
        )
        return self._project_to_list(data)

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList:
        return await self.create_list(space_id, name, **kwargs)

    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]:
        project_id = list_id
        # Get project name
        try:
            project = await self._get(f"/projects/{project_id}/")
            project_name = project.get("name", "")
        except Exception:
            project_name = ""

        # Get states for this project (for mapping)
        states = await self._get_states(project_id)
        state_lookup = {s["id"]: s for s in states}

        # Get work items
        work_items = await self._paginate_results(f"/projects/{project_id}/work-items/")

        tasks = []
        for wi in work_items:
            state_id = wi.get("state")
            state = state_lookup.get(state_id) if state_id else None
            tasks.append(self._work_item_to_task(wi, project_id, project_name, state))

        # Apply status filter if provided
        statuses = filters.get("statuses")
        if statuses:
            wanted = {s.lower() for s in statuses}
            tasks = [t for t in tasks if t.status and t.status.status.lower() in wanted]

        return tasks

    async def get_task(self, task_id: str) -> Task:
        # We need to find which project this work item belongs to.
        # Try all projects.
        projects = await self._paginate_results("/projects/")
        for project in projects:
            pid = project["id"]
            try:
                wi = await self._get(f"/projects/{pid}/work-items/{task_id}/")
                states = await self._get_states(pid)
                state_lookup = {s["id"]: s for s in states}
                state = state_lookup.get(wi.get("state"))
                return self._work_item_to_task(wi, pid, project.get("name", ""), state)
            except httpx.HTTPStatusError:
                continue
        raise NotFoundError(f"Work item not found: {task_id}")

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task:
        project_id = list_id
        project = await self._get(f"/projects/{project_id}/")
        project_name = project.get("name", "")

        payload: dict[str, Any] = {"name": name}

        # Description
        desc = kwargs.get("description")
        if desc:
            payload["description_html"] = f"<p>{desc}</p>"

        # Priority
        priority = kwargs.get("priority")
        if priority is not None:
            plane_pri = _ID_TO_PLANE_PRIORITY.get(str(priority), "medium")
            payload["priority"] = plane_pri

        # Status
        status = kwargs.get("status")
        if status and isinstance(status, str):
            state = await self._state_by_name(project_id, status)
            if state:
                payload["state"] = state["id"]

        wi = await self._post(f"/projects/{project_id}/work-items/", payload)

        states = await self._get_states(project_id)
        state_lookup = {s["id"]: s for s in states}
        state = state_lookup.get(wi.get("state"))
        return self._work_item_to_task(wi, project_id, project_name, state)

    async def update_task(self, task_id: str, **updates: Any) -> Task:
        # Find the project
        projects = await self._paginate_results("/projects/")
        for project in projects:
            pid = project["id"]
            try:
                await self._get(f"/projects/{pid}/work-items/{task_id}/")
            except httpx.HTTPStatusError:
                continue

            payload: dict[str, Any] = {}
            if "name" in updates:
                payload["name"] = updates["name"]
            if "description" in updates:
                payload["description_html"] = f"<p>{updates['description']}</p>"
            if "priority" in updates and updates["priority"] is not None:
                plane_pri = _ID_TO_PLANE_PRIORITY.get(str(updates["priority"]), "medium")
                payload["priority"] = plane_pri
            if "status" in updates and isinstance(updates["status"], str):
                state = await self._state_by_name(pid, updates["status"])
                if state:
                    payload["state"] = state["id"]

            wi = await self._patch(f"/projects/{pid}/work-items/{task_id}/", payload)
            states = await self._get_states(pid)
            state_lookup = {s["id"]: s for s in states}
            state = state_lookup.get(wi.get("state"))
            return self._work_item_to_task(wi, pid, project.get("name", ""), state)

        raise NotFoundError(f"Work item not found: {task_id}")

    async def delete_task(self, task_id: str) -> bool:
        projects = await self._paginate_results("/projects/")
        for project in projects:
            pid = project["id"]
            try:
                await self._delete(f"/projects/{pid}/work-items/{task_id}/")
                return True
            except httpx.HTTPStatusError:
                continue
        raise NotFoundError(f"Work item not found: {task_id}")

    async def get_task_comments(self, task_id: str) -> list[Comment]:
        projects = await self._paginate_results("/projects/")
        for project in projects:
            pid = project["id"]
            try:
                # Verify work item exists in this project
                await self._get(f"/projects/{pid}/work-items/{task_id}/")
                comments = await self._paginate_results(f"/projects/{pid}/work-items/{task_id}/comments/")
                return [self._to_comment(c) for c in comments]
            except httpx.HTTPStatusError:
                continue
        raise NotFoundError(f"Work item not found: {task_id}")

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment:
        projects = await self._paginate_results("/projects/")
        for project in projects:
            pid = project["id"]
            try:
                await self._get(f"/projects/{pid}/work-items/{task_id}/")
                data = await self._post(
                    f"/projects/{pid}/work-items/{task_id}/comments/",
                    {"comment_html": f"<p>{comment_text}</p>"},
                )
                return self._to_comment(data)
            except httpx.HTTPStatusError:
                continue
        raise NotFoundError(f"Work item not found: {task_id}")

    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]:
        """Search tasks across all projects by name substring."""
        projects = await self._paginate_results("/projects/")
        results: list[Task] = []
        needle = query.lower()

        for project in projects:
            pid = project["id"]
            pname = project.get("name", "")
            states = await self._get_states(pid)
            state_lookup = {s["id"]: s for s in states}

            work_items = await self._paginate_results(f"/projects/{pid}/work-items/")
            for wi in work_items:
                name = (wi.get("name") or "").lower()
                desc = (wi.get("description_stripped") or wi.get("description") or "").lower()
                if needle in name or needle in desc:
                    state = state_lookup.get(wi.get("state"))
                    results.append(self._work_item_to_task(wi, pid, pname, state))

        return results


def _strip_html(html: str) -> str:
    """Minimal HTML tag stripper for comment text."""
    import re

    return re.sub(r"<[^>]+>", "", html).strip()
