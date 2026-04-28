"""STUB -- owned by Agent A. Minimal output helpers for cross-agent imports.

This file will be replaced by Agent A's full implementation at merge time.
It provides the minimal surface area other agents import so that `just fc` passes.
"""

import json
from typing import Any, Literal

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..core.models import Comment, Space, Task, Team, User
from ..core.models import List as ClickUpList

Format = Literal["table", "json"]

_current_format: Format = "table"
_console = Console()


def get_format() -> Format:
    """Read the global format setting (set by --format on root command)."""
    return _current_format


def set_format(fmt: Format) -> None:
    """Set the global format (called from root callback)."""
    global _current_format
    _current_format = fmt


def render_user(user: User) -> None:
    """Render a single user."""
    if get_format() == "json":
        _console.print_json(json.dumps(user.model_dump(mode="json")))
    else:
        table = Table(title="User", show_header=False)
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")
        table.add_row("ID", str(user.id))
        table.add_row("Username", escape(user.username))
        table.add_row("Email", escape(user.email or "N/A"))
        table.add_row("Color", user.color or "N/A")
        table.add_row("Profile Picture", "Yes" if user.profilePicture else "No")
        _console.print(table)


def render_team(team: Team) -> None:
    """Render a single team."""
    if get_format() == "json":
        _console.print_json(json.dumps(team.model_dump(mode="json")))
    else:
        _console.print(f"[bold]{escape(team.name)}[/bold] (ID: {team.id})")


def render_teams(teams: list[Team]) -> None:
    """Render a list of teams."""
    if get_format() == "json":
        _console.print_json(json.dumps({"data": [t.model_dump(mode="json") for t in teams], "count": len(teams)}))
    else:
        for t in teams:
            render_team(t)


def render_space(space: Space) -> None:
    """Render a single space."""
    if get_format() == "json":
        _console.print_json(json.dumps(space.model_dump(mode="json")))
    else:
        _console.print(f"[bold]{escape(space.name)}[/bold] (ID: {space.id})")


def render_spaces(spaces: list[Space]) -> None:
    """Render a list of spaces."""
    if get_format() == "json":
        _console.print_json(json.dumps({"data": [s.model_dump(mode="json") for s in spaces], "count": len(spaces)}))
    else:
        for s in spaces:
            render_space(s)


def render_list(lst: ClickUpList) -> None:
    """Render a single list."""
    if get_format() == "json":
        _console.print_json(json.dumps(lst.model_dump(mode="json")))
    else:
        task_count = lst.task_count if lst.task_count is not None else "?"
        _console.print(f"[bold]{escape(lst.name)}[/bold] (ID: {lst.id}, tasks: {task_count})")


def render_lists(lists: list[ClickUpList]) -> None:
    """Render a list of lists."""
    if get_format() == "json":
        _console.print_json(json.dumps({"data": [item.model_dump(mode="json") for item in lists], "count": len(lists)}))
    else:
        for lst in lists:
            render_list(lst)


def render_task(task: Task) -> None:
    """Render a single task."""
    if get_format() == "json":
        _console.print_json(json.dumps(task.model_dump(mode="json")))
    else:
        status = task.status.status if task.status else "?"
        _console.print(f"  {escape(task.name)} [{status}] (ID: {task.id})")


def render_tasks(tasks: list[Task]) -> None:
    """Render a list of tasks."""
    if get_format() == "json":
        _console.print_json(json.dumps({"data": [t.model_dump(mode="json") for t in tasks], "count": len(tasks)}))
    else:
        for t in tasks:
            render_task(t)


def render_comments(comments: list[Comment]) -> None:
    """Render a list of comments."""
    if get_format() == "json":
        _console.print_json(json.dumps({"data": [c.model_dump(mode="json") for c in comments], "count": len(comments)}))
    else:
        for c in comments:
            _console.print(f"  [{c.user.username}] {escape(c.comment_text)}")


def render_kv(data: dict[str, object], title: str | None = None) -> None:
    """Render a key-value table."""
    if get_format() == "json":
        _console.print_json(json.dumps(data, default=str))
    else:
        table = Table(title=title, show_header=False)
        table.add_column("Key", style="cyan", width=25)
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(str(k), escape(str(v)) if v is not None else "[dim]None[/dim]")
        _console.print(table)


def render_message(msg: str, level: Literal["info", "success", "warn", "error"] = "info") -> None:
    """Render a status message."""
    style_map: dict[str, str] = {
        "info": "blue",
        "success": "green",
        "warn": "yellow",
        "error": "red",
    }
    style = style_map.get(level, "white")
    _console.print(f"[{style}]{msg}[/{style}]")


def _json_serial(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code."""
    return str(obj)
