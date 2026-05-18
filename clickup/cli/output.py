"""Output rendering for the ClickUp CLI.

Provides format-aware renderers (table / JSON) for every model the CLI displays.
Other modules import ``render_*`` helpers and call them; the active format is
set once by the ``--format`` callback on the root Typer app.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..core.models import Comment, Folder, Space, Task, Team, User
from ..core.models import List as ClickUpList

# ---------------------------------------------------------------------------
# Format state (set by root Typer callback, read by renderers)
# ---------------------------------------------------------------------------

Format = Literal["table", "json"]


class FormatChoice(StrEnum):
    """Enum wrapper for Typer CLI option compatibility."""

    table = "table"
    json = "json"


_current_format: Format = "json"

_console = Console()


def set_format(fmt: Format | FormatChoice) -> None:
    """Set the global output format (called by root ``--format`` callback)."""
    global _current_format  # noqa: PLW0603
    _current_format = fmt.value if isinstance(fmt, FormatChoice) else fmt


def get_format() -> Format:
    """Read the global format setting (set by ``--format`` on root command)."""
    return _current_format


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

_PRIORITY_LABELS: dict[str | None, str] = {
    "1": "urgent",
    "2": "high",
    "3": "normal",
    "4": "low",
}


def format_timestamp(epoch_ms: str | None, *, for_json: bool = False) -> str:
    """Convert a ClickUp epoch-millisecond string to a display string.

    * **JSON mode** returns ISO 8601 UTC, e.g. ``"2026-04-27T15:30:00Z"``.
    * **Table mode** returns a human-friendly date, e.g. ``"2026-04-27"``.

    Returns ``""`` (empty string) when the input is ``None`` or falsy.
    """
    if not epoch_ms:
        return ""
    try:
        ts = int(epoch_ms) / 1000.0
        dt = datetime.fromtimestamp(ts, tz=UTC)
    except (ValueError, OSError):
        return epoch_ms  # can't parse — pass through
    if for_json:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Priority helpers
# ---------------------------------------------------------------------------


def _priority_table_str(priority_info: Any) -> str:
    """Render priority for table display: ``"high (2)"``."""
    if priority_info is None:
        return "none"
    pid = getattr(priority_info, "id", None) or getattr(priority_info, "priority", None)
    label = _PRIORITY_LABELS.get(str(pid) if pid else None, "none")
    if pid:
        return f"{label} ({pid})"
    return "none"


def _priority_json(priority_info: Any) -> dict[str, Any]:
    """Return ``{"priority": <int|null>, "priority_label": <str>}`` for JSON."""
    if priority_info is None:
        return {"priority": None, "priority_label": "none"}
    pid = getattr(priority_info, "id", None) or getattr(priority_info, "priority", None)
    try:
        numeric = int(pid) if pid else None
    except (TypeError, ValueError):
        numeric = None
    label = _PRIORITY_LABELS.get(str(pid) if pid else None, "none")
    return {"priority": numeric, "priority_label": label}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print_json(data: Any) -> None:
    # Use print() instead of _console.print() so Rich doesn't interpret
    # square brackets in user data as markup tags.
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _mock_safe_attr(obj: Any, name: str) -> Any:
    """Return an attribute unless it is a dynamically-created unittest.mock value."""
    value = getattr(obj, name, None)
    if value.__class__.__module__.startswith("unittest.mock"):
        return None
    return value


_BRIEF_TASK_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "status",
    "priority",
    "priority_label",
    "assignees",
    "due_date",
    "url",
    "list",
    "source_list_id",
)


def _task_to_brief_dict(task: Task | Any) -> dict[str, Any]:
    """Stripped-down JSON projection for --brief mode.

    Cuts the ~30-field default down to identity + routing fields agents
    actually use. status is flattened to its name, priority to its int,
    assignees to a list of usernames.
    """
    full = _task_to_json_dict(task)
    brief: dict[str, Any] = {}
    for key in _BRIEF_TASK_FIELDS:
        if key not in full or full[key] is None:
            continue
        brief[key] = full[key]
    # Flatten nested objects to the shapes an agent typically wants.
    if isinstance(brief.get("status"), dict):
        brief["status"] = brief["status"].get("status")
    if isinstance(brief.get("assignees"), list):
        brief["assignees"] = [a.get("username") if isinstance(a, dict) else a for a in brief["assignees"]]
    if isinstance(brief.get("list"), dict):
        brief["list"] = {"id": brief["list"].get("id"), "name": brief["list"].get("name")}
    return brief


def _task_to_json_dict(task: Task | Any) -> dict[str, Any]:
    """Serialise a Task for JSON output with ISO timestamps and priority dual-display."""
    raw_dump = None
    model_dump = getattr(task, "model_dump", None)
    if callable(model_dump):
        try:
            raw_dump = model_dump(mode="json")
        except TypeError:
            raw_dump = None
    if isinstance(raw_dump, dict):
        d = raw_dump
    else:
        d = {
            key: value
            for key in ("id", "name", "description", "url", "source_list_id")
            if (value := _mock_safe_attr(task, key)) is not None
        }
    if (source_list_id := _mock_safe_attr(task, "source_list_id")) is not None:
        d["source_list_id"] = source_list_id
    # Convert epoch-ms timestamps to ISO 8601
    for ts_field in ("date_created", "date_updated", "date_closed", "date_done", "due_date", "start_date"):
        raw = d.get(ts_field)
        if raw:
            d[ts_field] = format_timestamp(str(raw), for_json=True)
    # Priority dual-display
    d.update(_priority_json(_mock_safe_attr(task, "priority")))
    return d


def _comment_to_json_dict(comment: Comment | Any) -> dict[str, Any]:
    """Serialise a Comment for JSON output with ISO timestamp."""
    raw_dump = comment.model_dump(mode="json") if callable(getattr(comment, "model_dump", None)) else None
    if isinstance(raw_dump, dict):
        d = raw_dump
    else:
        d = {
            key: value
            for key in ("id", "comment_text", "date", "resolved")
            if (value := _mock_safe_attr(comment, key)) is not None
        }
    if d.get("date"):
        d["date"] = format_timestamp(str(d["date"]), for_json=True)
    return d


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------


def render_user(user: User) -> None:
    """Render a single User."""
    if get_format() == "json":
        _print_json(user.model_dump(mode="json"))
        return
    table = Table(title="User", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("ID", str(user.id))
    table.add_row("Username", escape(user.username))
    table.add_row("Email", escape(user.email))
    if user.color:
        table.add_row("Color", user.color)
    if user.role is not None:
        table.add_row("Role", str(user.role))
    _console.print(table)


def render_team(team: Team) -> None:
    """Render a single Team/Workspace."""
    if get_format() == "json":
        _print_json(team.model_dump(mode="json"))
        return
    table = Table(title="Workspace", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("ID", team.id)
    table.add_row("Name", escape(team.name))
    table.add_row("Color", team.color)
    table.add_row("Members", str(len(team.members)))
    _console.print(table)


def render_teams(teams: list[Team]) -> None:
    """Render a list of Teams/Workspaces."""
    if get_format() == "json":
        _print_json({"data": [t.model_dump(mode="json") for t in teams], "count": len(teams)})
        return
    table = Table(title="Workspaces", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Color", style="green")
    table.add_column("Members", style="blue")
    for team in teams:
        table.add_row(team.id, escape(team.name), team.color, str(len(team.members)))
    _console.print(table)


def render_space(space: Space) -> None:
    """Render a single Space."""
    if get_format() == "json":
        _print_json(space.model_dump(mode="json"))
        return
    table = Table(title="Space", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("ID", space.id)
    table.add_row("Name", escape(space.name))
    table.add_row("Private", "Yes" if space.private else "No")
    table.add_row("Statuses", str(len(space.statuses)))
    _console.print(table)


def render_spaces(spaces: list[Space]) -> None:
    """Render a list of Spaces."""
    if get_format() == "json":
        _print_json({"data": [s.model_dump(mode="json") for s in spaces], "count": len(spaces)})
        return
    table = Table(title="Spaces", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Private", style="yellow")
    table.add_column("Statuses", style="green")
    for space in spaces:
        table.add_row(space.id, escape(space.name), "Yes" if space.private else "No", str(len(space.statuses)))
    _console.print(table)


def render_list(lst: ClickUpList) -> None:
    """Render a single ClickUp List."""
    if get_format() == "json":
        _print_json(lst.model_dump(mode="json"))
        return
    table = Table(title=f"List: {escape(lst.name)}", show_header=False)
    table.add_column("Field", style="cyan", width=15)
    table.add_column("Value")
    table.add_row("ID", lst.id)
    table.add_row("Name", escape(lst.name))
    table.add_row("Content", escape(lst.content) if lst.content else "None")
    table.add_row("Tasks", str(lst.task_count) if lst.task_count is not None else "N/A")
    if lst.orderindex is not None:
        table.add_row("Order Index", str(lst.orderindex))
    table.add_row("Due Date", format_timestamp(lst.due_date) if lst.due_date else "None")
    table.add_row("Start Date", format_timestamp(lst.start_date) if lst.start_date else "None")
    table.add_row("Archived", "Yes" if lst.archived else "No")
    if lst.assignee is not None:
        table.add_row("Assignee", escape(lst.assignee.username))
    if lst.folder is not None and lst.folder.name:
        table.add_row("Folder", escape(lst.folder.name))
    if lst.space is not None and lst.space.name:
        table.add_row("Space", escape(lst.space.name))
    statuses = (lst.model_extra or {}).get("statuses")
    if isinstance(statuses, list) and statuses:
        names = ", ".join(
            escape(s.get("status", "") if isinstance(s, dict) else getattr(s, "status", str(s))) for s in statuses
        )
        table.add_row("Statuses", names)
    _console.print(table)


def render_lists(lists: list[ClickUpList]) -> None:
    """Render a list of ClickUp Lists."""
    if get_format() == "json":
        _print_json({"data": [lst.model_dump(mode="json") for lst in lists], "count": len(lists)})
        return
    table = Table(title="Lists", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Tasks", style="green")
    table.add_column("Due Date", style="yellow")
    table.add_column("Archived", style="red")
    for lst in lists:
        table.add_row(
            lst.id,
            escape(lst.name),
            str(lst.task_count) if lst.task_count is not None else "N/A",
            format_timestamp(lst.due_date) if lst.due_date else "None",
            "Yes" if lst.archived else "No",
        )
    _console.print(table)


def render_folders(folders: list[Folder]) -> None:
    """Render a list of Folders."""
    if get_format() == "json":
        _print_json({"data": [f.model_dump(mode="json") for f in folders], "count": len(folders)})
        return
    table = Table(title="Folders", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Hidden", style="yellow")
    table.add_column("Task Count", style="green")
    for folder in folders:
        table.add_row(folder.id, escape(folder.name), "Yes" if folder.hidden else "No", str(folder.task_count))
    _console.print(table)


def render_users(users: list[User], *, title: str = "Users") -> None:
    """Render a list of Users (e.g. workspace members)."""
    if get_format() == "json":
        _print_json({"data": [u.model_dump(mode="json") for u in users], "count": len(users)})
        return
    table = Table(title=title, show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="bold")
    table.add_column("Email", style="green")
    table.add_column("Role", style="magenta")
    table.add_column("Color", style="yellow")
    for u in users:
        table.add_row(
            str(u.id),
            escape(u.username),
            escape(u.email),
            str(u.role) if u.role is not None else "None",
            u.color or "None",
        )
    _console.print(table)


def render_hierarchy(data: dict[str, Any]) -> None:
    """Render a nested workspace → space → folder → list hierarchy.

    ``data`` shape::

        {
            "workspaces": [
                {
                    "id": ..., "name": ...,
                    "spaces": [
                        {
                            "id": ..., "name": ...,
                            "folders": [
                                {"id": ..., "name": ..., "lists": [{"id": ..., "name": ..., "task_count": N}]}
                            ],
                            "folderless_lists": [{"id": ..., "name": ..., "task_count": N}]
                        }
                    ]
                }
            ]
        }
    """
    if get_format() == "json":
        _print_json(data)
        return

    from rich.tree import Tree

    tree = Tree("🏢 ClickUp Hierarchy")
    for workspace in data.get("workspaces", []):
        ws_node = tree.add(f"🏢 [bold cyan]{escape(workspace['name'])}[/bold cyan] ([dim]{workspace['id']}[/dim])")
        for space in workspace.get("spaces", []):
            sp_node = ws_node.add(f"📁 [blue]{escape(space['name'])}[/blue] ([dim]{space['id']}[/dim])")
            for folder in space.get("folders", []):
                f_node = sp_node.add(f"📂 [yellow]{escape(folder['name'])}[/yellow] ([dim]{folder['id']}[/dim])")
                for lst in folder.get("lists", []):
                    f_node.add(
                        f"📋 [green]{escape(lst['name'])}[/green] ([dim]{lst['id']}[/dim]) - "
                        f"{lst.get('task_count', '?')} tasks"
                    )
            folderless = space.get("folderless_lists", [])
            if folderless:
                fl_node = sp_node.add("📂 [yellow]Folderless Lists[/yellow]")
                for lst in folderless:
                    fl_node.add(
                        f"📋 [green]{escape(lst['name'])}[/green] ([dim]{lst['id']}[/dim]) - "
                        f"{lst.get('task_count', '?')} tasks"
                    )
    _console.print(tree)


def render_task(task: Task, *, brief: bool = False) -> None:
    """Render a single Task with full detail. With ``brief=True`` the JSON
    output is a trimmed projection (id/name/status/priority/...) and the
    table output keeps only the same key rows."""
    if get_format() == "json":
        _print_json(_task_to_brief_dict(task) if brief else _task_to_json_dict(task))
        return

    table = Table(title=f"Task: {escape(task.name)}", show_header=False)
    table.add_column("Field", style="cyan", width=15)
    table.add_column("Value")

    table.add_row("ID", task.id)
    table.add_row("Name", escape(task.name))
    if not brief:
        table.add_row("Description", escape(task.description) if task.description else "None")
    table.add_row("Status", escape(task.status.status) if task.status else "Unknown")
    table.add_row(
        "Assignees",
        escape(", ".join(a.username for a in task.assignees)) if task.assignees else "Unassigned",
    )
    table.add_row("Priority", _priority_table_str(task.priority))
    table.add_row("Due Date", format_timestamp(task.due_date) or "None")
    if not brief:
        table.add_row("Created", format_timestamp(task.date_created) or "Unknown")
        table.add_row("Updated", format_timestamp(task.date_updated) or "Unknown")
    table.add_row("URL", task.url or "None")

    _console.print(table)


def render_tasks(tasks: list[Task], *, brief: bool = False) -> None:
    """Render a list of Tasks. ``brief=True`` switches to a stripped JSON
    projection (still wrapped in the ``{"data": [...], "count": N}`` envelope)."""
    if get_format() == "json":
        serialize = _task_to_brief_dict if brief else _task_to_json_dict
        _print_json({"data": [serialize(t) for t in tasks], "count": len(tasks)})
        return

    table = Table(title="Tasks", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status", style="green")
    table.add_column("Assignees", style="blue")
    table.add_column("Priority", style="yellow")
    table.add_column("Due Date", style="red")

    for task in tasks:
        status = escape(task.status.status) if task.status else "Unknown"
        assignees = escape(", ".join(a.username for a in task.assignees)) if task.assignees else "Unassigned"
        priority = _priority_table_str(task.priority)
        due_date = format_timestamp(task.due_date) or "None"

        table.add_row(task.id, escape(task.name), status, assignees, priority, due_date)

    _console.print(table)


def render_comments(comments: list[Comment]) -> None:
    """Render a list of Comments."""
    if get_format() == "json":
        _print_json({"data": [_comment_to_json_dict(c) for c in comments], "count": len(comments)})
        return

    table = Table(title="Comments", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Author", style="blue")
    table.add_column("Date", style="yellow")
    table.add_column("Comment", style="white")
    table.add_column("Resolved", style="green")

    for comment in comments:
        table.add_row(
            comment.id,
            escape(comment.user.username),
            format_timestamp(comment.date),
            escape(comment.comment_text),
            "Yes" if comment.resolved else "No",
        )

    _console.print(table)


def render_comment(comment: Comment) -> None:
    """Render a single Comment."""
    if get_format() == "json":
        _print_json(_comment_to_json_dict(comment))
        return

    table = Table(title="Comment", show_header=False)
    table.add_column("Field", style="cyan", width=15)
    table.add_column("Value")
    table.add_row("ID", comment.id)
    table.add_row("Author", escape(comment.user.username))
    table.add_row("Date", format_timestamp(comment.date))
    table.add_row("Comment", escape(comment.comment_text))
    table.add_row("Resolved", "Yes" if comment.resolved else "No")
    _console.print(table)


def render_kv(data: dict[str, object], title: str | None = None) -> None:
    """Render an arbitrary key/value mapping."""
    if get_format() == "json":
        _print_json(data)
        return
    table = Table(title=title, show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for k, v in data.items():
        table.add_row(escape(str(k)), escape(str(v)))
    _console.print(table)


def render_statuses(statuses: list[dict[str, Any]], *, list_id: str, list_name: str | None = None) -> None:
    """Render statuses available for a ClickUp list."""
    if get_format() == "json":
        _print_json(
            {
                "list_id": list_id,
                "list_name": list_name,
                "data": statuses,
                "count": len(statuses),
            }
        )
        return

    title = f"Statuses: {list_name}" if list_name else "Statuses"
    table = Table(title=title, show_header=True)
    table.add_column("Status", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Color", style="yellow")
    table.add_column("Order", style="blue")
    for status in statuses:
        table.add_row(
            escape(str(status.get("status") or "")),
            escape(str(status.get("type") or "")),
            escape(str(status.get("color") or "")),
            escape(str(status.get("orderindex") or "")),
        )
    _console.print(table)


def render_message(msg: str, level: Literal["info", "success", "warn", "error"] = "info") -> None:
    """Print a styled one-line message. Respects ``--format json`` by emitting
    ``{"message": ..., "level": ...}`` on stderr (info/success/warn/error all
    route to stderr in JSON mode so stdout stays a single data envelope).
    """
    if get_format() == "json":
        # Commentary, warnings, and errors are all stderr-bound in JSON mode
        # so the data envelope on stdout stays a single parseable JSON value.
        typer.echo(json.dumps({"message": msg, "level": level}), err=True)
        return
    if level in ("error", "warn"):
        # Plain text on stderr — keep it dependency-free and trivially
        # capturable by test runners and shell pipelines.
        typer.echo(msg, err=True)
        return
    style_map: dict[str, str] = {
        "info": "bold",
        "success": "bold green",
    }
    style = style_map.get(level, "bold")
    _console.print(f"[{style}]{escape(msg)}[/{style}]")


def render_error(msg: str, hint: str | None = None) -> None:
    """Emit an error to stderr.

    In ``--format json`` mode emits ``{"error": msg, "hint": hint}`` to stderr
    (``hint`` omitted when ``None``) so stdout pipelines (which expect data
    JSON) are not corrupted. In table mode emits the message and the hint
    on separate stderr lines.

    Caller is responsible for raising ``typer.Exit(code)`` after this returns.
    Convention: ``code=1`` for runtime/API errors, ``code=2`` for usage errors
    (missing required flags, invalid input, etc.).
    """
    if get_format() == "json":
        payload: dict[str, str] = {"error": msg}
        if hint:
            payload["hint"] = hint
        typer.echo(json.dumps(payload), err=True)
    else:
        typer.echo(msg, err=True)
        if hint:
            typer.echo(hint, err=True)
