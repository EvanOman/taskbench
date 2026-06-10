"""Planka task provider — maps Planka's Kanban model to the TaskProvider protocol.

Concept mapping (TaskProvider -> Planka):
    Team/Workspace  -> synthetic singleton derived from logged-in user
    Space           -> Planka Project
    Folder          -> no-op (returns [] / synthetic placeholder)
    List (CU)       -> Planka Board
    Status          -> Planka List (column) within a Board
    Task            -> Planka Card
    Comment         -> Planka Comment (Action)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Self

# Planka SDK (v2 API)
from plankapy.v2 import Planka
from plankapy.v2 import models as pk_models
from rich.console import Console

from .config import Config
from .exceptions import NotFoundError, ValidationError
from .models import Comment, Folder, Space, Task, Team, TeamMember, User
from .models import List as ClickUpList


def _now_ms() -> str:
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def _iso_to_ms(iso_str: str | None) -> str | None:
    """Convert ISO datetime string to milliseconds timestamp string."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Synthetic IDs: Planka uses large integers; we stringify them for ClickUp
# model compat. We prefix with 'pk_' for clarity in debugging.
# --------------------------------------------------------------------------- #


def _sid(planka_id: int | str) -> str:
    """Stringify a Planka ID for ClickUp model consumption."""
    return str(planka_id)


# --------------------------------------------------------------------------- #
# Status helpers
# --------------------------------------------------------------------------- #

_STATUS_COLORS: dict[str, str] = {
    "to do": "#87909f",
    "in progress": "#2f80ed",
    "review": "#f2c94c",
    "complete": "#27ae60",
}

_STATUS_TYPES: dict[str, str] = {
    "to do": "open",
    "in progress": "custom",
    "review": "custom",
    "complete": "closed",
}


def _status_info(list_name: str, orderindex: int = 0) -> dict[str, Any]:
    """Build a StatusInfo-compatible dict from a Planka List (column) name."""
    key = list_name.lower()
    return {
        "status": key,
        "color": _STATUS_COLORS.get(key, "#cccccc"),
        "type": _STATUS_TYPES.get(key, "custom"),
        "orderindex": orderindex,
    }


# --------------------------------------------------------------------------- #
# Converters
# --------------------------------------------------------------------------- #


def _safe_timestamp(card_schema: dict[str, Any], key: str) -> str | None:
    """Safely extract a timestamp from a card's raw schema dict."""
    raw = card_schema.get(key)
    if raw is None:
        return None
    return _iso_to_ms(str(raw))


def _card_to_task(card: pk_models.Card, board: pk_models.Board | None = None) -> Task:
    """Convert a Planka Card to a ClickUp Task model."""
    # Determine which Planka List (column) the card is in -> that's the status
    planka_list = card.list
    status_name = planka_list.name.lower() if planka_list else "unknown"
    status = _status_info(status_name)

    board_ref = board or card.board
    board_id = _sid(board_ref.id) if board_ref else ""
    board_name = board_ref.name if board_ref else ""

    # Use raw schema to avoid plankapy's fromisoformat bug on None values
    schema = card.schema if hasattr(card, "schema") else {}
    created_ms = _safe_timestamp(schema, "createdAt") or _now_ms()
    updated_ms = _safe_timestamp(schema, "updatedAt") or created_ms

    # Get URL safely (plankapy sometimes doesn't have it)
    try:
        card_url = card.url
    except Exception:
        card_url = None

    return Task(
        id=_sid(card.id),
        name=card.name,
        description=card.description or "",
        status=status,
        date_created=created_ms,
        date_updated=updated_ms,
        archived=False,
        assignees=[],
        priority=None,
        list={"id": board_id, "name": board_name},
        url=card_url or f"planka://card/{card.id}",
    )


def _board_to_list(board: pk_models.Board) -> ClickUpList:
    """Convert a Planka Board to a ClickUp List model."""
    # Count cards across all columns
    card_count = len(board.cards) if board.cards else 0

    # Build statuses from the board's Planka Lists (columns)
    statuses = []
    for idx, pl in enumerate(board.lists or []):
        statuses.append(_status_info(pl.name, idx))

    project = board.project
    space_ref = {"id": _sid(project.id), "name": project.name} if project else None

    return ClickUpList(
        id=_sid(board.id),
        name=board.name,
        task_count=card_count,
        space=space_ref,
        statuses=statuses,
    )


def _project_to_space(project: pk_models.Project) -> Space:
    """Convert a Planka Project to a ClickUp Space model."""
    # Gather statuses from all boards' columns
    all_statuses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for board in project.boards or []:
        for _idx, pl in enumerate(board.lists or []):
            key = pl.name.lower()
            if key not in seen:
                seen.add(key)
                all_statuses.append(_status_info(key, len(all_statuses)))

    return Space(
        id=_sid(project.id),
        name=project.name,
        private=True,
        multiple_assignees=True,
        features={},
        statuses=all_statuses,
    )


def _pk_comment_to_comment(action: pk_models.Comment, user_info: User) -> Comment:
    """Convert a Planka Comment to a ClickUp Comment model."""
    created_ms = _iso_to_ms(str(action.created_at)) if action.created_at else _now_ms()
    if hasattr(action, "text"):
        comment_text = action.text
    elif hasattr(action, "data") and action.data:
        comment_text = str(action.data.get("text", ""))
    else:
        comment_text = ""

    return Comment(
        id=_sid(action.id),
        comment=[],
        comment_text=comment_text,
        user=user_info,
        date=created_ms or _now_ms(),
        resolved=False,
    )


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #


class PlankaProvider:
    """Provider adapter backed by a Planka instance (v2 API via plankapy)."""

    SYNTHETIC_TEAM_ID = "planka_workspace"

    def __init__(self, config: Config | None = None, console: Console | None = None):
        self.config = config or Config()
        self.console = console or Console()
        self._url = os.getenv("PLANKA_URL", "http://localhost:18920")
        self._username = os.getenv("PLANKA_USERNAME") or os.getenv("PLANKA_EMAIL") or "admin"
        self._password = os.getenv("PLANKA_PASSWORD", "")
        self._planka: Planka | None = None
        self._user_cache: User | None = None

    def _connect(self) -> Planka:
        if self._planka is None:
            self._planka = Planka(self._url)
            self._planka.login(
                username=self._username,
                password=self._password,
                accept_terms=True,
            )
        return self._planka

    @property
    def planka(self) -> Planka:
        return self._connect()

    async def __aenter__(self) -> Self:
        self._connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._planka = None

    # -- User / Auth -------------------------------------------------------- #

    def _me_as_user(self) -> User:
        if self._user_cache is None:
            me = self.planka.me
            self._user_cache = User(
                id=int(str(me.id)[-9:]),  # Truncate large Planka IDs for int field
                username=me.name or "admin",
                email=me.schema.get("email", "admin@local") if hasattr(me, "schema") else "admin@local",
            )
        return self._user_cache

    async def get_user(self) -> User:
        return self._me_as_user()

    async def validate_auth(self) -> tuple[bool, str, User | None]:
        try:
            user = self._me_as_user()
            return True, f"Planka provider active ({user.username})", user
        except Exception as e:
            return False, f"Planka auth failed: {e}", None

    # -- Teams (synthetic) -------------------------------------------------- #

    async def get_teams(self) -> list[Team]:
        user = self._me_as_user()
        return [
            Team(
                id=self.SYNTHETIC_TEAM_ID,
                name="Planka Workspace",
                color="#2f80ed",
                members=[TeamMember(user=user)],
            )
        ]

    async def get_team(self, team_id: str) -> Team:
        teams = await self.get_teams()
        for team in teams:
            if team.id == team_id:
                return team
        raise NotFoundError(f"Workspace not found: {team_id}")

    async def get_team_members(self, team_id: str) -> list[User]:
        team = await self.get_team(team_id)
        return [m.user for m in team.members]

    # -- Spaces (= Planka Projects) ---------------------------------------- #

    async def get_spaces(self, team_id: str) -> list[Space]:
        return [_project_to_space(p) for p in self.planka.projects]

    async def get_space(self, space_id: str) -> Space:
        for project in self.planka.projects:
            if _sid(project.id) == space_id:
                return _project_to_space(project)
        raise NotFoundError(f"Space not found: {space_id}")

    # -- Folders (no-op) ---------------------------------------------------- #

    async def get_folders(self, space_id: str) -> list[Folder]:
        # Planka has no folder concept; return a synthetic placeholder
        return [
            Folder(
                id=f"folder_{space_id}",
                name="Default",
                orderindex=0,
                override_statuses=False,
                hidden=False,
                space={"id": space_id, "name": ""},
                task_count="0",
            )
        ]

    async def get_folder(self, folder_id: str) -> Folder:
        # Extract space_id from synthetic folder_id
        space_id = folder_id.replace("folder_", "")
        folders = await self.get_folders(space_id)
        if folders:
            return folders[0]
        raise NotFoundError(f"Folder not found: {folder_id}")

    async def create_folder(self, space_id: str, name: str, **kwargs: Any) -> Folder:
        # Planka has no folder concept; every space exposes one synthetic
        # "Default" folder. Refuse rather than silently pretend.
        _ = (space_id, name, kwargs)
        raise ValidationError(
            "Planka has no folders. Create lists directly in the space "
            "(or use the synthetic 'folder_<space_id>' default folder)."
        )

    # -- Lists (= Planka Boards) ------------------------------------------- #

    async def get_lists(self, folder_id: str) -> list[ClickUpList]:
        # folder_id is synthetic: "folder_{space_id}"
        space_id = folder_id.replace("folder_", "")
        return await self.get_folderless_lists(space_id)

    async def get_folderless_lists(self, space_id: str) -> list[ClickUpList]:
        for project in self.planka.projects:
            if _sid(project.id) == space_id:
                return [_board_to_list(b) for b in (project.boards or [])]
        raise NotFoundError(f"Space not found: {space_id}")

    async def get_list(self, list_id: str) -> ClickUpList:
        for project in self.planka.projects:
            for board in project.boards or []:
                if _sid(board.id) == list_id:
                    return _board_to_list(board)
        raise NotFoundError(f"List not found: {list_id}")

    async def create_list(self, folder_id: str, name: str, **kwargs: Any) -> ClickUpList:
        space_id = folder_id.replace("folder_", "")
        return await self.create_folderless_list(space_id, name, **kwargs)

    async def create_folderless_list(self, space_id: str, name: str, **kwargs: Any) -> ClickUpList:
        for project in self.planka.projects:
            if _sid(project.id) == space_id:
                board = project.create_board(name=name, position="bottom")
                # Create default status columns
                for status_name in ["to do", "in progress", "review", "complete"]:
                    board.create_list(name=status_name, position="bottom")
                return _board_to_list(board)
        raise NotFoundError(f"Space not found: {space_id}")

    # -- Tasks (= Planka Cards) -------------------------------------------- #

    def _find_board(self, list_id: str) -> pk_models.Board:
        """Find a Planka Board by ID across all projects."""
        for project in self.planka.projects:
            for board in project.boards or []:
                if _sid(board.id) == list_id:
                    return board
        raise NotFoundError(f"List not found: {list_id}")

    def _find_card(self, task_id: str) -> pk_models.Card:
        """Find a Planka Card by ID across all projects/boards."""
        for project in self.planka.projects:
            for board in project.boards or []:
                for card in board.cards or []:
                    if _sid(card.id) == task_id:
                        return card
        raise NotFoundError(f"Task not found: {task_id}")

    async def get_tasks(self, list_id: str, **filters: Any) -> list[Task]:
        board = self._find_board(list_id)
        tasks = [_card_to_task(card, board) for card in (board.cards or [])]

        # Apply status filter if provided
        statuses = filters.get("statuses")
        if statuses:
            wanted = {str(s).lower() for s in statuses}
            tasks = [t for t in tasks if (t.status.status if t.status else "").lower() in wanted]

        if filters.get("include_closed") is False:
            tasks = [t for t in tasks if (t.status.type if t.status else "") != "closed"]

        return tasks

    async def get_task(self, task_id: str) -> Task:
        card = self._find_card(task_id)
        return _card_to_task(card)

    async def create_task(self, list_id: str, name: str, **kwargs: Any) -> Task:
        board = self._find_board(list_id)
        status_name = kwargs.pop("status", "to do")
        if isinstance(status_name, dict):
            status_name = status_name.get("status", "to do")
        status_name = str(status_name).lower()

        # Find the correct Planka List (column) for the status
        target_list = None
        for pl in board.lists or []:
            if pl.name.lower() == status_name:
                target_list = pl
                break

        if target_list is None:
            # Default to first list if status not found
            lists = board.lists or []
            target_list = lists[0] if lists else None
            if target_list is None:
                raise ValidationError(f"Board {list_id} has no columns")

        description = kwargs.pop("description", None)
        # Drop extra kwargs that Planka doesn't understand
        kwargs.pop("priority", None)

        card = target_list.create_card(
            name=name,
            description=description,
            position="bottom",
        )
        return _card_to_task(card, board)

    async def update_task(self, task_id: str, **updates: Any) -> Task:
        card = self._find_card(task_id)

        # Handle status change -> move card to different Planka List
        new_status = updates.pop("status", None)
        if new_status is not None:
            if isinstance(new_status, dict):
                new_status = new_status.get("status", "")
            new_status = str(new_status).lower()
            board = card.board
            for pl in board.lists or []:
                if pl.name.lower() == new_status:
                    card.move(pl)
                    break

        # Handle other updates
        update_kwargs: dict[str, Any] = {}
        if "name" in updates:
            update_kwargs["name"] = updates["name"]
        if "description" in updates:
            update_kwargs["description"] = updates["description"]

        if update_kwargs:
            card.update(**update_kwargs)

        # Re-fetch for fresh data
        card.sync()
        return _card_to_task(card)

    async def delete_task(self, task_id: str) -> bool:
        card = self._find_card(task_id)
        card.delete()
        return True

    # -- Comments ----------------------------------------------------------- #

    async def get_task_comments(self, task_id: str) -> list[Comment]:
        card = self._find_card(task_id)
        user = self._me_as_user()
        comments = []
        for action in card.comments or []:
            comments.append(_pk_comment_to_comment(action, user))
        return comments

    async def create_comment(self, task_id: str, comment_text: str, **kwargs: Any) -> Comment:
        card = self._find_card(task_id)
        action = card.comment(comment_text)
        user = self._me_as_user()
        return _pk_comment_to_comment(action, user)

    # -- Search ------------------------------------------------------------- #

    async def search_tasks(self, team_id: str, query: str, **filters: Any) -> list[Task]:
        needle = query.lower()
        results: list[Task] = []
        for project in self.planka.projects:
            for board in project.boards or []:
                for card in board.cards or []:
                    if needle in card.name.lower() or needle in (card.description or "").lower():
                        results.append(_card_to_task(card, board))
        return results

    # -- Raw request (best-effort) ------------------------------------------ #

    async def raw_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Best-effort raw request passthrough; limited for Planka."""
        raise ValidationError(f"raw_request not fully supported for Planka: {method} {endpoint}")
