"""Todoist task provider — adapts the Todoist REST API to the TaskProvider protocol."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Self

from rich.console import Console

from .config import Config
from .exceptions import NotFoundError, ValidationError
from .models import Comment, Folder, ListRef, PriorityInfo, Space, SpaceRef, StatusInfo, Task, Team, TeamMember, User
from .models import List as ClickUpList


def _now_ms() -> str:
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def _iso_to_ms(iso: str | None) -> str | None:
    """Convert ISO 8601 datetime string to epoch milliseconds."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except (ValueError, AttributeError):
        return None


# Todoist priority is inverted: 4=urgent(highest), 1=normal(lowest)
# ClickUp/seed: 1=urgent, 2=high, 3=normal, 4=low
_TODOIST_TO_CLICKUP_PRIORITY = {4: "1", 3: "2", 2: "3", 1: "4"}
_CLICKUP_TO_TODOIST_PRIORITY = {"1": 4, "2": 3, "3": 2, "4": 1}

# Synthetic IDs for ClickUp concepts that don't exist in Todoist
_SYNTH_TEAM_ID = "todoist_personal"
_SYNTH_SPACE_ID = "todoist_workspace"
_SYNTH_FOLDER_ID = "todoist_nofolder"


async def _collect_pages(paginator: Any) -> list[Any]:
    """Exhaust an async paginator from todoist-api-python and return flat list."""
    items: list[Any] = []
    async for page in paginator:
        items.extend(page)
    return items


class TodoistProvider:
    """Provider adapter that maps Todoist to the TaskProvider protocol.

    Concept mapping:
      Team     -> synthetic "Personal" workspace
      Space    -> synthetic (wraps the workspace)
      Folder   -> no-op (empty list / synthetic placeholder)
      List     -> Todoist Project
      Status   -> Todoist Section within a project
      Task     -> Todoist Task
      Comment  -> Todoist Comment
    """

    def __init__(self, config: Config | None = None, console: Console | None = None):
        self.config = config or Config()
        self.console = console or Console()
        self._token = os.getenv("TODOIST_TOKEN") or self.config.get("todoist_token") or ""
        self._api: Any = None  # TodoistAPIAsync, lazily created
        # Cache section lookups: project_id -> {section_name_lower: Section}
        self._section_cache: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> Self:
        from todoist_api_python.api_async import TodoistAPIAsync

        self._api = TodoistAPIAsync(self._token)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._api is not None:
            await self._api.close()
            self._api = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sections_for_project(self, project_id: str) -> dict[str, Any]:
        """Return {section_name_lower: Section} for a project, with caching."""
        if project_id not in self._section_cache:
            sections = await _collect_pages(await self._api.get_sections(project_id=project_id))
            self._section_cache[project_id] = {s.name.lower(): s for s in sections}
        return self._section_cache[project_id]

    async def _section_name(self, project_id: str, section_id: str | None) -> str:
        """Resolve a section_id to its display name (used as status)."""
        if not section_id:
            return "to do"
        sections = await self._sections_for_project(project_id)
        for _name, sec in sections.items():
            if sec.id == section_id:
                return sec.name
        return "to do"

    async def _section_id_for_status(self, project_id: str, status_name: str) -> str | None:
        """Resolve a status name to a section_id."""
        sections = await self._sections_for_project(project_id)
        sec = sections.get(status_name.lower())
        return sec.id if sec else None

    def _todoist_task_to_model(self, t: Any, status_name: str = "to do") -> Task:
        """Convert a todoist-api-python Task to our pydantic Task model."""
        cu_priority = _TODOIST_TO_CLICKUP_PRIORITY.get(t.priority, "3")
        created_ms = _iso_to_ms(str(t.created_at)) or _now_ms()
        updated_ms = _iso_to_ms(str(t.updated_at)) or created_ms

        return Task(
            id=t.id,
            name=t.content,
            description=t.description or None,
            text_content=t.description or None,
            status=StatusInfo(status=status_name),
            date_created=created_ms,
            date_updated=updated_ms,
            archived=False,
            assignees=[],
            priority=PriorityInfo(id=cu_priority, priority=cu_priority),
            list=ListRef(id=t.project_id, name=None),
            url=t.url,
        )

    def _todoist_project_to_list(self, p: Any) -> ClickUpList:
        """Convert a todoist-api-python Project to our pydantic List model."""
        return ClickUpList(
            id=p.id,
            name=p.name,
            task_count=None,
            space=SpaceRef(id=_SYNTH_SPACE_ID, name="Todoist Workspace"),
        )

    def _todoist_comment_to_model(self, c: Any) -> Comment:
        """Convert a todoist-api-python Comment to our pydantic Comment model."""
        return Comment(
            id=c.id,
            comment=[],
            comment_text=c.content,
            user=User(id=int(c.poster_id), username="todoist_user", email=""),
            date=_iso_to_ms(str(c.posted_at)) or _now_ms(),
            resolved=False,
        )

    # ------------------------------------------------------------------
    # TaskProvider protocol implementation
    # ------------------------------------------------------------------

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        raise ValidationError(f"raw_request not supported for Todoist provider: {method} {endpoint}")

    async def get_user(self) -> User:
        return User(id=0, username="Todoist User", email="todoist@local")

    async def validate_auth(self) -> tuple[bool, str, User | None]:
        try:
            projects = await _collect_pages(await self._api.get_projects())
            user = await self.get_user()
            return True, f"Todoist auth valid ({len(projects)} projects)", user
        except Exception as e:
            return False, f"Todoist auth failed: {e}", None

    async def get_teams(self) -> list[Team]:
        return [
            Team(
                id=_SYNTH_TEAM_ID,
                name="Todoist Personal",
                color="#e44332",
                members=[TeamMember(user=await self.get_user())],
            )
        ]

    async def get_team(self, team_id: str) -> Team:
        teams = await self.get_teams()
        if teams and teams[0].id == team_id:
            return teams[0]
        raise NotFoundError(f"Team not found: {team_id}")

    async def get_team_members(self, team_id: str) -> list[User]:
        return [await self.get_user()]

    async def get_spaces(self, team_id: str) -> list[Space]:
        return [
            Space(
                id=_SYNTH_SPACE_ID,
                name="Todoist Workspace",
                private=False,
                multiple_assignees=False,
                features={},
                statuses=[
                    StatusInfo(status="to do", type="open", color="#87909f", orderindex=0),
                    StatusInfo(status="in progress", type="custom", color="#2f80ed", orderindex=1),
                    StatusInfo(status="review", type="custom", color="#f2c94c", orderindex=2),
                    StatusInfo(status="complete", type="closed", color="#27ae60", orderindex=3),
                ],
            )
        ]

    async def get_space(self, space_id: str) -> Space:
        spaces = await self.get_spaces(_SYNTH_TEAM_ID)
        for s in spaces:
            if s.id == space_id:
                return s
        raise NotFoundError(f"Space not found: {space_id}")

    async def get_folders(self, space_id: str) -> list[Folder]:
        return []

    async def get_folder(self, folder_id: str) -> Folder:
        raise NotFoundError(f"Folders are not supported in Todoist provider: {folder_id}")

    async def get_lists(self, folder_id: str) -> list[ClickUpList]:
        # Todoist has no folders; return all projects as folderless
        return []

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]:
        projects = await _collect_pages(await self._api.get_projects())
        return [self._todoist_project_to_list(p) for p in projects if not p.is_archived]

    async def get_list(self, list_id: str) -> ClickUpList:
        try:
            project = await self._api.get_project(list_id)
            return self._todoist_project_to_list(project)
        except Exception as e:
            raise NotFoundError(f"List (project) not found: {list_id}") from e

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList:
        # Create a Todoist project (ignore folder_id)
        project = await self._api.add_project(name=name, view_style="board")
        return self._todoist_project_to_list(project)

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList:
        project = await self._api.add_project(name=name, view_style="board")
        return self._todoist_project_to_list(project)

    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]:
        all_tasks = await _collect_pages(await self._api.get_tasks(project_id=list_id))
        result: list[Task] = []
        for t in all_tasks:
            status_name = await self._section_name(t.project_id, t.section_id)
            result.append(self._todoist_task_to_model(t, status_name))

        # Apply status filter if present
        statuses_filter = filters.get("statuses")
        if statuses_filter:
            wanted = {str(s).lower() for s in statuses_filter}
            result = [t for t in result if (t.status.status.lower() if t.status else "") in wanted]

        return result

    async def get_task(self, task_id: str) -> Task:
        try:
            t = await self._api.get_task(task_id)
            status_name = await self._section_name(t.project_id, t.section_id)
            return self._todoist_task_to_model(t, status_name)
        except Exception as e:
            raise NotFoundError(f"Task not found: {task_id}") from e

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task:
        # Map ClickUp-style kwargs to Todoist kwargs
        description = kwargs.pop("description", None)
        status = kwargs.pop("status", None)
        priority = kwargs.pop("priority", None)

        section_id = None
        if status:
            section_id = await self._section_id_for_status(list_id, str(status))

        todoist_priority = 1
        if priority is not None:
            todoist_priority = _CLICKUP_TO_TODOIST_PRIORITY.get(str(priority), 1)

        t = await self._api.add_task(
            content=name,
            description=description or "",
            project_id=list_id,
            section_id=section_id,
            priority=todoist_priority,
        )
        status_name = status or "to do"
        return self._todoist_task_to_model(t, str(status_name))

    async def update_task(self, task_id: str, **updates: Any) -> Task:
        # Get current task first
        current = await self._api.get_task(task_id)

        # Handle status change (= move to a different section)
        new_status = updates.pop("status", None)
        if new_status:
            section_id = await self._section_id_for_status(current.project_id, str(new_status))
            if section_id:
                await self._api.move_task(task_id, section_id=section_id)

        # Map priority
        priority = updates.pop("priority", None)
        todoist_priority = None
        if priority is not None:
            todoist_priority = _CLICKUP_TO_TODOIST_PRIORITY.get(str(priority), None)

        # Map name -> content
        content = updates.pop("name", None)
        description = updates.pop("description", None)

        update_kwargs: dict[str, Any] = {}
        if content is not None:
            update_kwargs["content"] = content
        if description is not None:
            update_kwargs["description"] = description
        if todoist_priority is not None:
            update_kwargs["priority"] = todoist_priority

        if update_kwargs:
            await self._api.update_task(task_id, **update_kwargs)

        # Re-fetch to return updated state
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        try:
            return await self._api.delete_task(task_id)
        except Exception as e:
            raise NotFoundError(f"Task not found: {task_id}") from e

    async def get_task_comments(self, task_id: str) -> list[Comment]:
        comments = await _collect_pages(await self._api.get_comments(task_id=task_id))
        return [self._todoist_comment_to_model(c) for c in comments]

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment:
        c = await self._api.add_comment(content=comment_text, task_id=task_id)
        return self._todoist_comment_to_model(c)

    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]:
        # Todoist filter_tasks uses Todoist query language; fall back to substring search
        all_projects = await _collect_pages(await self._api.get_projects())
        results: list[Task] = []
        needle = query.lower()
        for project in all_projects:
            if project.is_archived:
                continue
            tasks = await _collect_pages(await self._api.get_tasks(project_id=project.id))
            for t in tasks:
                if needle in t.content.lower() or needle in (t.description or "").lower():
                    status_name = await self._section_name(t.project_id, t.section_id)
                    results.append(self._todoist_task_to_model(t, status_name))
        return results
