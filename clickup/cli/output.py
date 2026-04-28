# STUB — agent A owns this file.
# This provides the contract API so task.py compiles.
# Will be replaced when Agent A's branch merges.

"""Output formatting for ClickUp CLI."""

from datetime import UTC, datetime
from typing import Any, Literal

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..core.models import Comment, Space, Task, Team, User
from ..core.models import List as ClickUpList

Format = Literal["table", "json"]

_format: Format = "table"
_console = Console(width=200)

PRIORITY_LABELS: dict[str, str] = {
    "1": "urgent",
    "2": "high",
    "3": "normal",
    "4": "low",
}


def get_format() -> Format:
    """Read the global format setting (set by --format on root command)."""
    return _format


def set_format(fmt: Format) -> None:
    """Set the global format setting."""
    global _format
    _format = fmt


def format_timestamp(ts: str | None) -> str:
    """Convert ClickUp epoch-ms timestamp to human-friendly string.

    For table output: '2026-04-27 (yesterday)' style.
    For JSON output: ISO 8601 UTC string.
    """
    if not ts:
        return "None"
    try:
        epoch_ms = int(ts)
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
        if get_format() == "json":
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        now = datetime.now(tz=UTC)
        delta = now - dt
        if delta.days == 0:
            return dt.strftime("%Y-%m-%d") + " (today)"
        elif delta.days == 1:
            return dt.strftime("%Y-%m-%d") + " (yesterday)"
        elif delta.days < 7:
            return dt.strftime("%Y-%m-%d") + f" ({delta.days}d ago)"
        else:
            return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return ts


def format_priority(priority_info: Any) -> str:
    """Format priority as '2 (high)' style."""
    if not priority_info:
        return "None"
    p = priority_info.priority if hasattr(priority_info, "priority") else str(priority_info)
    if not p:
        return "None"
    label = PRIORITY_LABELS.get(str(p), "")
    if label:
        return f"{p} ({label})"
    return str(p)


def render_user(user: User) -> None:
    """Render a single user."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps(user.model_dump(mode="json")))
    else:
        _console.print(f"User: {escape(user.username)} ({user.email})")


def render_team(team: Team) -> None:
    """Render a single team."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps(team.model_dump(mode="json")))
    else:
        _console.print(f"Team: {escape(team.name)} (ID: {team.id})")


def render_teams(teams: list[Team]) -> None:
    """Render a list of teams."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps({"data": [t.model_dump(mode="json") for t in teams], "count": len(teams)}))
    else:
        for team in teams:
            render_team(team)


def render_space(space: Space) -> None:
    """Render a single space."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps(space.model_dump(mode="json")))
    else:
        _console.print(f"Space: {escape(space.name)} (ID: {space.id})")


def render_spaces(spaces: list[Space]) -> None:
    """Render a list of spaces."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps({"data": [s.model_dump(mode="json") for s in spaces], "count": len(spaces)}))
    else:
        for space in spaces:
            render_space(space)


def render_list(lst: ClickUpList) -> None:
    """Render a single list."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps(lst.model_dump(mode="json")))
    else:
        _console.print(f"List: {escape(lst.name)} (ID: {lst.id})")


def render_lists(lists: list[ClickUpList]) -> None:
    """Render a list of lists."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps({"data": [lst.model_dump(mode="json") for lst in lists], "count": len(lists)}))
    else:
        for lst in lists:
            render_list(lst)


def _safe_str(value: object, default: str = "None") -> str:
    """Safely convert a value to string, handling Mock objects and None."""
    if value is None:
        return default
    try:
        s = str(value)
        # Mock objects return strings like "<Mock ...>" or raise TypeError
        if s.startswith("<Mock") or s.startswith("<MagicMock"):
            return default
        return s
    except (TypeError, ValueError):
        return default


def _safe_list(value: object) -> list[Any]:
    """Safely convert to a list, returning [] if not iterable or is Mock."""
    if value is None:
        return []
    try:
        result = list(value)  # type: ignore[arg-type]
        return result
    except (TypeError, ValueError):
        return []


def render_task(task: Task) -> None:
    """Render a single task with all detail fields."""
    import json as _json

    if get_format() == "json":
        data = task.model_dump(mode="json")
        # Add priority_label for JSON
        if task.priority and task.priority.priority:
            data["priority_label"] = PRIORITY_LABELS.get(str(task.priority.priority), "")
        _console.print_json(_json.dumps(data))
    else:
        table = Table(
            title=f"Task: {escape(_safe_str(task.name, 'Unknown'))}",
            show_header=False,
        )
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")

        table.add_row("ID", _safe_str(task.id))
        table.add_row("Name", escape(_safe_str(task.name)))
        table.add_row("Description", escape(_safe_str(task.description)))
        status = task.status
        table.add_row(
            "Status",
            _safe_str(status.status if status and hasattr(status, "status") else None, "Unknown"),
        )
        assignees = _safe_list(getattr(task, "assignees", []))
        if assignees:
            table.add_row(
                "Assignees",
                ", ".join([escape(_safe_str(a.username)) for a in assignees]),
            )
        else:
            table.add_row("Assignees", "Unassigned")
        table.add_row("Priority", format_priority(task.priority))
        table.add_row("Due Date", format_timestamp(_safe_str(task.due_date)))
        table.add_row(
            "Start Date",
            format_timestamp(_safe_str(getattr(task, "start_date", None))),
        )
        table.add_row(
            "Created",
            format_timestamp(_safe_str(getattr(task, "date_created", None))),
        )
        table.add_row(
            "Updated",
            format_timestamp(_safe_str(getattr(task, "date_updated", None))),
        )
        table.add_row("URL", _safe_str(getattr(task, "url", None)))

        # Extended detail fields
        creator = getattr(task, "creator", None)
        if creator and hasattr(creator, "username"):
            table.add_row("Creator", escape(_safe_str(creator.username)))

        tags = _safe_list(getattr(task, "tags", []))
        if tags:
            tag_names = []
            for t in tags:
                name = getattr(t, "name", None) if hasattr(t, "name") else _safe_str(t)
                tag_names.append(escape(_safe_str(name)))
            table.add_row("Tags", ", ".join(tag_names))
        else:
            table.add_row("Tags", "None")

        table.add_row("Parent", _safe_str(getattr(task, "parent", None)))

        # Custom fields
        custom_fields = _safe_list(getattr(task, "custom_fields", []))
        if custom_fields:
            cf_parts = []
            for cf in custom_fields:
                cf_name = _safe_str(getattr(cf, "name", "?"))
                cf_val = _safe_str(getattr(cf, "value", ""))
                cf_parts.append(f"{escape(cf_name)}={cf_val}")
            table.add_row("Custom Fields", ", ".join(cf_parts))
        else:
            table.add_row("Custom Fields", "None")

        # Time tracking
        time_est = getattr(task, "time_estimate", None)
        if isinstance(time_est, int | float) and time_est:
            hours = time_est / 3_600_000
            table.add_row("Time Estimate", f"{hours:.1f}h")
        else:
            table.add_row("Time Estimate", "None")

        time_sp = getattr(task, "time_spent", None)
        if isinstance(time_sp, int | float) and time_sp:
            hours = time_sp / 3_600_000
            table.add_row("Time Tracked", f"{hours:.1f}h")
        else:
            table.add_row("Time Tracked", "None")

        # Watchers
        watchers = _safe_list(getattr(task, "watchers", []))
        if watchers:
            table.add_row(
                "Watchers",
                ", ".join([escape(_safe_str(w.username)) for w in watchers]),
            )
        else:
            table.add_row("Watchers", "None")

        # Location context
        task_list = getattr(task, "list", None)
        if task_list and hasattr(task_list, "id"):
            list_name = _safe_str(getattr(task_list, "name", ""))
            table.add_row("List", f"{escape(list_name)} ({task_list.id})")
        task_folder = getattr(task, "folder", None)
        if task_folder and hasattr(task_folder, "id"):
            folder_name = _safe_str(getattr(task_folder, "name", ""))
            table.add_row("Folder", f"{escape(folder_name)} ({task_folder.id})")
        task_space = getattr(task, "space", None)
        if task_space and hasattr(task_space, "id"):
            space_name = _safe_str(getattr(task_space, "name", ""))
            table.add_row("Space", f"{escape(space_name)} ({task_space.id})")

        _console.print(table)


def render_tasks(tasks: list[Task]) -> None:
    """Render a list of tasks as a table."""
    import json as _json

    if get_format() == "json":
        data_list = []
        for t in tasks:
            d = t.model_dump(mode="json")
            if t.priority and t.priority.priority:
                d["priority_label"] = PRIORITY_LABELS.get(str(t.priority.priority), "")
            data_list.append(d)
        _console.print_json(_json.dumps({"data": data_list, "count": len(data_list)}))
    else:
        table = Table(title="Tasks", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Status", style="green")
        table.add_column("Assignees", style="blue")
        table.add_column("Priority", style="yellow")
        table.add_column("Due Date", style="red")
        table.add_column("Updated", style="dim")

        for task in tasks:
            status_obj = task.status
            status = _safe_str(
                status_obj.status if status_obj and hasattr(status_obj, "status") else None,
                "Unknown",
            )
            task_assignees = _safe_list(getattr(task, "assignees", []))
            assignees = (
                ", ".join([escape(_safe_str(a.username)) for a in task_assignees]) if task_assignees else "Unassigned"
            )
            priority = format_priority(task.priority)
            due_date = format_timestamp(_safe_str(task.due_date))
            updated = format_timestamp(_safe_str(getattr(task, "date_updated", None)))

            table.add_row(
                _safe_str(task.id),
                escape(_safe_str(task.name)),
                status,
                assignees,
                priority,
                due_date,
                updated,
            )

        _console.print(table)


def render_comments(comments: list[Comment]) -> None:
    """Render a list of comments."""
    import json as _json

    if get_format() == "json":
        _console.print_json(
            _json.dumps({"data": [c.model_dump(mode="json") for c in comments], "count": len(comments)})
        )
    else:
        table = Table(title="Comments", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Author", style="blue")
        table.add_column("Text", style="white")
        table.add_column("Date", style="dim")
        table.add_column("Resolved", style="green")

        for comment in comments:
            table.add_row(
                comment.id,
                escape(comment.user.username),
                escape(comment.comment_text),
                format_timestamp(comment.date),
                "Yes" if comment.resolved else "No",
            )

        _console.print(table)


def render_kv(data: dict[str, object], title: str | None = None) -> None:
    """Render key-value pairs."""
    import json as _json

    if get_format() == "json":
        _console.print_json(_json.dumps(data, default=str))
    else:
        table = Table(title=title, show_header=False)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(str(k), escape(str(v)))
        _console.print(table)


def render_message(msg: str, level: Literal["info", "success", "warn", "error"] = "info") -> None:
    """Render a status message."""
    styles = {
        "info": "",
        "success": "[green]",
        "warn": "[yellow]",
        "error": "[red]",
    }
    end_styles = {
        "info": "",
        "success": "[/green]",
        "warn": "[/yellow]",
        "error": "[/red]",
    }
    _console.print(f"{styles[level]}{escape(msg)}{end_styles[level]}")
