"""ClickUp data models using pydantic."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatusEnum(StrEnum):
    """Task status enumeration."""

    OPEN = "open"
    IN_PROGRESS = "in progress"
    REVIEW = "review"
    CLOSED = "closed"


class PriorityEnum(StrEnum):
    """Task priority enumeration."""

    URGENT = "1"
    HIGH = "2"
    NORMAL = "3"
    LOW = "4"


class StatusInfo(BaseModel):
    """Task status information from the API."""

    model_config = ConfigDict(extra="allow")

    status: str
    color: str | None = None
    type: str | None = None
    orderindex: int | None = None


class PriorityInfo(BaseModel):
    """Task priority information from the API."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    priority: str | None = None
    color: str | None = None
    orderindex: str | None = None


class Tag(BaseModel):
    """Task tag model."""

    model_config = ConfigDict(extra="allow")

    name: str
    tag_fg: str | None = None
    tag_bg: str | None = None
    creator: int | None = None


class ChecklistItem(BaseModel):
    """Checklist item model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    orderindex: int | None = None
    assignee: "Assignee | None" = None
    group_assignee: str | None = None
    resolved: bool = False
    parent: str | None = None
    date_created: str | None = None
    children: list["ChecklistItem"] = Field(default_factory=list)


class Checklist(BaseModel):
    """Task checklist model."""

    model_config = ConfigDict(extra="allow")

    id: str
    task_id: str | None = None
    name: str
    date_created: str | None = None
    orderindex: int | None = None
    creator: int | None = None
    resolved: int = 0
    unresolved: int = 0
    items: list[ChecklistItem] = Field(default_factory=list)


class Dependency(BaseModel):
    """Task dependency model."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    depends_on: str
    type: int | None = None
    date_created: str | None = None
    userid: str | None = None
    workspace_id: str | None = None


class LinkedTask(BaseModel):
    """Linked task reference model."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    link_id: str
    date_created: str | None = None
    userid: str | None = None
    workspace_id: str | None = None


class SpaceRef(BaseModel):
    """Reference to a space (used in nested contexts)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None


class FolderRef(BaseModel):
    """Reference to a folder (used in nested contexts)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    hidden: bool | None = None
    access: bool | None = None


class ListRef(BaseModel):
    """Reference to a list (used in nested contexts)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    access: bool | None = None


class CustomField(BaseModel):
    """ClickUp custom field model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str
    value: Any | None = None


class User(BaseModel):
    """ClickUp user model."""

    model_config = ConfigDict(extra="allow")

    id: int
    username: str
    email: str
    color: str | None = None
    profilePicture: str | None = None
    role: int | str | None = None  # API returns int, but could be string


class Assignee(BaseModel):
    """Task assignee model."""

    model_config = ConfigDict(extra="allow")

    id: int
    username: str
    color: str | None = None
    email: str | None = None


class List(BaseModel):
    """ClickUp list model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    orderindex: int | None = None
    content: str | None = None
    status: StatusInfo | None = None
    priority: PriorityInfo | None = None
    assignee: User | None = None
    task_count: int | None = None
    due_date: str | None = None
    start_date: str | None = None
    folder: FolderRef | None = None
    space: SpaceRef | None = None
    archived: bool = False


class Folder(BaseModel):
    """ClickUp folder model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    orderindex: int
    override_statuses: bool
    hidden: bool
    space: SpaceRef
    task_count: str
    archived: bool = False
    lists: list["List"] = Field(default_factory=list)


class Space(BaseModel):
    """ClickUp space model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    private: bool
    statuses: list[StatusInfo] = Field(default_factory=list)
    multiple_assignees: bool
    features: dict[str, Any] = Field(default_factory=dict)  # Dynamic feature flags
    archived: bool = False


class TeamMember(BaseModel):
    """Team member wrapper model."""

    model_config = ConfigDict(extra="allow")
    user: User


class Team(BaseModel):
    """ClickUp team/workspace model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    color: str
    avatar: str | None = None
    members: list[TeamMember] = Field(default_factory=list)


class Task(BaseModel):
    """ClickUp task model."""

    model_config = ConfigDict(extra="allow")

    id: str
    custom_id: str | None = None
    name: str
    text_content: str | None = None
    description: str | None = None
    status: StatusInfo | None = None
    orderindex: str | None = None
    date_created: str | None = None
    date_updated: str | None = None
    date_closed: str | None = None
    date_done: str | None = None
    archived: bool = False
    creator: User | None = None
    assignees: list[Assignee] = Field(default_factory=list)
    watchers: list[User] = Field(default_factory=list)
    checklists: list[Checklist] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    parent: str | None = None
    priority: PriorityInfo | None = None
    due_date: str | None = None
    start_date: str | None = None
    points: int | None = None
    time_estimate: int | None = None
    time_spent: int | None = None
    custom_fields: list[CustomField] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    linked_tasks: list[LinkedTask] = Field(default_factory=list)
    team_id: str | None = None
    url: str | None = None
    permission_level: str | None = None
    list: ListRef | None = None
    project: dict[str, Any] | None = None  # Project structure varies
    folder: FolderRef | None = None
    space: SpaceRef | None = None


class Workspace(BaseModel):
    """ClickUp workspace model (alias for Team in v3 API)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    color: str
    avatar: str | None = None
    members: list[User] = Field(default_factory=list)


class Comment(BaseModel):
    """ClickUp comment model."""

    model_config = ConfigDict(extra="allow")

    id: str
    comment: list[dict[str, Any]] = Field(default_factory=list)
    comment_text: str
    # ClickUp's create-comment response omits the author; only reads include it.
    user: User | None = None
    date: str
    resolved: bool = False


class Webhook(BaseModel):
    """ClickUp webhook model."""

    model_config = ConfigDict(extra="allow")

    id: str
    userid: int
    team_id: int
    endpoint: str
    client_id: str
    events: list[str]
    task_id: str | None = None
    list_id: str | None = None
    folder_id: str | None = None
    space_id: str | None = None
    health: dict[str, Any] = Field(default_factory=dict)
    secret: str | None = None
