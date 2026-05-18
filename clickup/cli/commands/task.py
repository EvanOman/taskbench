"""Task management commands."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

import typer
from rich.console import Console

from ...core import ClickUpError, Config, TaskProvider, get_provider, provider_requires_credentials
from ..output import (
    get_format,
    render_comment,
    render_comments,
    render_error,
    render_kv,
    render_message,
    render_statuses,
    render_task,
    render_tasks,
)
from ..utils import run_async

app = typer.Typer(help="Task management")
console = Console()

# Subgroup for comments
comments_app = typer.Typer(help="Task comment operations")
app.add_typer(comments_app, name="comments")


async def get_client() -> TaskProvider:
    """Get configured task provider."""
    config = Config()
    if provider_requires_credentials(config) and not config.has_credentials():
        console.print(
            "[red]Error: No ClickUp API token configured. Set CLICKUP_API_KEY in your "
            "environment (or .env), or run 'clickup config set-token <token>'.[/red]"
        )
        raise typer.Exit(1)
    return get_provider(config, console)


def _resolve_list_id(list_id: str | None) -> str | None:
    """Resolve a list ID, expanding configured aliases."""
    return Config().resolve_list_id(list_id)


def _split_csv(value: str | None) -> list[str]:
    """Split a comma-separated CLI value, trimming whitespace and rejecting empties."""
    if value is None:
        return []
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part for part in parts):
        _usage_error(f"Error: empty value in comma-separated argument '{value}'.")
    return parts


def _resolve_list_ids(list_id: str | None, *, all_lists: bool = False) -> list[str]:
    """Resolve one or more list IDs/aliases from CLI input."""
    config = Config()
    if all_lists:
        aliases: dict[str, str] = config.get("default_lists") or {}
        if not aliases:
            _usage_error("Error: --all-lists requires configured default_lists aliases.")
        return list(aliases.values())

    raw_values = _split_csv(list_id)
    if not raw_values:
        resolved = config.resolve_list_id(None)
        return [resolved] if resolved else []
    return [resolved for raw in raw_values if (resolved := config.resolve_list_id(raw))]


_RELATIVE_TIME_RE = re.compile(r"^(?P<count>\d+)(?P<unit>[dhw])$")


def _epoch_ms(value: str) -> int:
    """Parse an epoch-ms, ISO date/datetime, or relative duration into epoch milliseconds."""
    trimmed = value.strip()
    if not trimmed:
        _usage_error("Error: date filter value is empty.")
    if trimmed.isdigit():
        return int(trimmed)

    relative = _RELATIVE_TIME_RE.match(trimmed.lower())
    if relative:
        count = int(relative.group("count"))
        unit = relative.group("unit")
        delta = {
            "d": timedelta(days=count),
            "h": timedelta(hours=count),
            "w": timedelta(weeks=count),
        }[unit]
        return int((datetime.now(tz=UTC) - delta).timestamp() * 1000)

    try:
        if len(trimmed) == 10 and trimmed[4] == "-" and trimmed[7] == "-":
            dt = datetime.fromisoformat(trimmed).replace(tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
    except ValueError as exc:
        _ = exc
        _usage_error(
            "Error: date filters accept epoch milliseconds, YYYY-MM-DD, ISO datetime, or relative values like 7d."
        )
    return int(dt.timestamp() * 1000)


def _set_exclusive_date_filter(filters: dict[str, Any], key: str, values: list[tuple[str, str | None]]) -> None:
    """Set a ClickUp date filter when exactly one of several aliases is provided."""
    provided = [(name, value) for name, value in values if value is not None]
    if len(provided) > 1:
        names = ", ".join(name for name, _value in provided)
        _usage_error(f"Error: conflicting date filters for {key}: {names}.")
    if provided:
        filters[key] = _epoch_ms(provided[0][1])


def _annotate_source_list(task: Any, list_id: str) -> Any:
    """Attach source list metadata when a fanout query merges multiple lists."""
    try:
        task.source_list_id = list_id
    except (AttributeError, TypeError):
        pass
    return task


async def _resolve_workspace_id(client: TaskProvider, workspace_id: str | None) -> str:
    """Resolve workspace ID from arg, config, or single-workspace auto-detect."""
    if workspace_id:
        return workspace_id
    config = Config()
    default = config.get("default_team_id")
    if default:
        return default
    # Auto-detect: if the user belongs to exactly one workspace, use it
    teams = await client.get_teams()
    if len(teams) == 1:
        return teams[0].id
    if not teams:
        render_error("Error: No workspaces found for this account.")
        raise typer.Exit(1)
    render_error("Error: Multiple workspaces found. Please specify --workspace-id.")
    raise typer.Exit(1)


def _parse_sort(sort: str | None, reverse_flag: bool) -> tuple[str | None, bool]:
    """Parse ``--sort`` (with optional direction) and the ``--reverse`` flag.

    Returns ``(field, descending)``. Accepted forms for ``sort``:

        field          → (field, reverse_flag)        # plain, --reverse applies
        field:asc      → (field, False)
        field:desc     → (field, True)
        -field         → (field, True)                 # git/jq-style
        +field         → (field, False)

    Surrounding whitespace is trimmed. Direction tokens are case-insensitive.
    Empty/whitespace-only input, empty field after prefix/colon, invalid
    direction, and combining an explicit direction with ``--reverse`` are
    all usage errors (exit 2) so an agent never gets silent input swallowing
    or double-toggle behavior.
    """
    if sort is None:
        return None, reverse_flag

    sort = sort.strip()
    if not sort:
        _usage_error("Error: --sort value is empty.")

    field: str
    explicit_desc: bool | None = None

    if sort.startswith("-"):
        field, explicit_desc = sort[1:].strip(), True
    elif sort.startswith("+"):
        field, explicit_desc = sort[1:].strip(), False
    elif ":" in sort:
        raw_field, _, direction = sort.partition(":")
        field = raw_field.strip()
        direction = direction.strip().lower()
        if direction == "desc":
            explicit_desc = True
        elif direction == "asc":
            explicit_desc = False
        else:
            _usage_error(f"Error: invalid sort direction '{direction}'. Use 'asc' or 'desc'.")
    else:
        field = sort

    if explicit_desc is None:
        return field, reverse_flag

    if not field:
        _usage_error("Error: --sort field name is empty.")
    if reverse_flag:
        _usage_error("Error: --reverse can't be combined with an explicit direction in --sort.")

    return field, explicit_desc


@app.command("list")
def list_tasks(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to get tasks from"),
    all_lists: bool = typer.Option(False, "--all-lists", help="Query every configured default_lists alias"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status; comma-separated values allowed"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Filter by assignee"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of tasks to show"),
    created_since: str | None = typer.Option(None, "--created-since", help="Created after relative time, e.g. 7d"),
    created_after: str | None = typer.Option(None, "--created-after", help="Created after date/epoch-ms"),
    created_before: str | None = typer.Option(None, "--created-before", help="Created before date/epoch-ms"),
    updated_since: str | None = typer.Option(None, "--updated-since", help="Updated after relative time, e.g. 7d"),
    updated_after: str | None = typer.Option(None, "--updated-after", help="Updated after date/epoch-ms"),
    updated_before: str | None = typer.Option(None, "--updated-before", help="Updated before date/epoch-ms"),
    sort: str | None = typer.Option(
        None,
        "--sort",
        "--order-by",
        help=(
            "Sort tasks by: created, updated, due_date, priority. "
            "Direction syntax: 'updated:desc', '-updated' (desc), '+updated' or 'updated' (asc). "
            "When direction is implicit, --reverse decides."
        ),
    ),
    reverse: bool = typer.Option(
        False,
        "--reverse",
        help="Sort descending. Illegal when --sort already has an explicit direction.",
    ),
) -> None:
    """List tasks from a ClickUp list."""
    order_by, descending = _parse_sort(sort, reverse)

    async def _list_tasks() -> None:
        list_ids_to_use = _resolve_list_ids(list_id, all_lists=all_lists)

        if not list_ids_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                filters: dict[str, Any] = {}
                if status:
                    filters["statuses"] = _split_csv(status)
                if assignee:
                    filters["assignees"] = [assignee]
                if order_by:
                    filters["order_by"] = order_by
                if descending:
                    filters["reverse"] = "true"
                _set_exclusive_date_filter(
                    filters,
                    "date_created_gt",
                    [("--created-since", created_since), ("--created-after", created_after)],
                )
                _set_exclusive_date_filter(filters, "date_created_lt", [("--created-before", created_before)])
                _set_exclusive_date_filter(
                    filters,
                    "date_updated_gt",
                    [("--updated-since", updated_since), ("--updated-after", updated_after)],
                )
                _set_exclusive_date_filter(filters, "date_updated_lt", [("--updated-before", updated_before)])

                tasks = []
                include_source = len(list_ids_to_use) > 1
                for list_id_to_use in list_ids_to_use:
                    list_tasks_result = await client.get_tasks(list_id_to_use, **filters)
                    if include_source:
                        list_tasks_result = [_annotate_source_list(task, list_id_to_use) for task in list_tasks_result]
                    tasks.extend(list_tasks_result)
                if not tasks:
                    render_message("No tasks found.", "warn")
                    return

                # Apply limit
                tasks = tasks[:limit]
                render_tasks(tasks)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_list_tasks())


@app.command("get")
def get_task(task_id: str = typer.Argument(..., help="Task ID")) -> None:
    """Get detailed information about a specific task.

    Shows all available fields including tags, parent, custom fields,
    time estimate, time tracked, watchers, and list/folder/space context.
    """

    async def _get_task() -> None:
        try:
            async with await get_client() as client:
                task = await client.get_task(task_id)
                render_task(task)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_get_task())


@app.command("mine")
def my_tasks(
    workspace_id: str | None = typer.Option(
        None,
        "--workspace-id",
        "-w",
        help="Workspace/team ID (defaults to default_team_id or auto-detected single workspace)",
    ),
    limit: int = typer.Option(50, "--limit", help="Maximum number of tasks to show"),
) -> None:
    """List tasks assigned to the authenticated user.

    Searches across the workspace for tasks assigned to you. Uses the default
    workspace from config, or auto-detects if you belong to exactly one workspace.
    """

    async def _my_tasks() -> None:
        try:
            async with await get_client() as client:
                # Get the authenticated user's ID
                user = await client.get_user()
                ws_id = await _resolve_workspace_id(client, workspace_id)

                # Search for tasks assigned to this user across the workspace
                # ClickUp API expects assignees[] as repeated query params
                tasks = await client.search_tasks(
                    ws_id,
                    "",
                    **{"assignees[]": [str(user.id)]},
                )
                if not tasks:
                    render_message("No tasks assigned to you.", "warn")
                    return

                tasks = tasks[:limit]
                render_tasks(tasks)
                render_message(f"\nShowing {len(tasks)} task(s) assigned to {user.username}.", "info")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_my_tasks())


@app.command("create")
def create_task(
    name: str = typer.Argument(..., help="Task name"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID or alias to create task in"),
    description: str | None = typer.Option(None, "--description", "-d", help="Task description"),
    priority: int | None = typer.Option(None, "--priority", "-p", help="Priority (1=urgent, 4=low)"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Assignee user ID"),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
    status: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Initial status (e.g. 'on-deck'). Falls back to config default_status, then list default.",
    ),
) -> None:
    """Create a new task."""

    async def _create_task() -> None:
        list_id_to_use = _resolve_list_id(list_id)

        if not list_id_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        config = Config()
        status_to_use = status or config.get("default_status")

        try:
            task_data: dict[str, Any] = {"name": name}

            if description:
                task_data["description"] = description
            if priority:
                task_data["priority"] = priority
            if assignee:
                task_data["assignees"] = [assignee]
            if due_date:
                task_data["due_date"] = due_date
            if status_to_use:
                task_data["status"] = status_to_use

            async with await get_client() as client:
                task = await client.create_task(list_id_to_use, **task_data)
                if get_format() == "json":
                    render_task(task)
                    return
                render_message(f"Created task: {task.name} (ID: {task.id})", "success")
                if task.url:
                    render_message(f"URL: {task.url}", "info")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_create_task())


@app.command("update")
def update_task(
    task_id: str | None = typer.Argument(None, help="Task ID"),
    task_ids: str | None = typer.Option(None, "--task-ids", help="Comma-separated task IDs to update"),
    name: str | None = typer.Option(None, "--name", "-n", help="New task name"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description (pass '' to clear)"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    priority: int | None = typer.Option(None, "--priority", "-p", help="New priority (1-4)"),
    due_date: str | None = typer.Option(None, "--due-date", help="New due date (ms timestamp)"),
    archived: bool | None = typer.Option(None, "--archived/--unarchived", help="Archive state"),
) -> None:
    """Update a task. Only fields you pass are changed; everything else stays the same."""

    async def _update_task() -> None:
        if task_id is not None and task_ids is not None:
            _usage_error("Error: pass TASK_ID either as a positional argument OR via --task-ids, not both.")
        target_ids = [task_id] if task_id is not None else _split_csv(task_ids)
        if not target_ids:
            _usage_error("Error: Task ID or --task-ids is required.")

        updates: dict[str, Any] = {}
        # `is not None` so callers can pass '' to clear text fields.
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if status is not None:
            updates["status"] = status
        if priority is not None:
            updates["priority"] = priority
        if due_date is not None:
            updates["due_date"] = due_date
        if archived is not None:
            updates["archived"] = archived

        if not updates:
            render_message("No updates specified.", "warn")
            return

        try:
            async with await get_client() as client:
                tasks = [await client.update_task(target_id, **updates) for target_id in target_ids]
                if get_format() == "json":
                    if len(tasks) == 1:
                        render_task(tasks[0])
                    else:
                        render_tasks(tasks)
                    return
                if len(tasks) == 1:
                    render_message(f"Updated task: {tasks[0].name} (ID: {tasks[0].id})", "success")
                else:
                    render_message(f"Updated {len(tasks)} tasks.", "success")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_update_task())


async def _do_status_change_many(task_ids: list[str], status: str) -> None:
    """Shared implementation for `task status` and short verb aliases."""
    try:
        async with await get_client() as client:
            tasks = [await client.update_task(task_id, status=status) for task_id in task_ids]
            if get_format() == "json":
                if len(tasks) == 1:
                    render_task(tasks[0])
                else:
                    render_tasks(tasks)
                return
            if len(tasks) == 1:
                render_message(f"Updated task status: {tasks[0].name} -> {status}", "success")
            else:
                render_message(f"Updated {len(tasks)} task statuses -> {status}", "success")
    except ClickUpError as e:
        render_error(f"ClickUp API Error: {e}")
        raise typer.Exit(1) from e


async def _do_status_change(task_id: str, status: str) -> None:
    """Shared single-task status update wrapper."""
    await _do_status_change_many([task_id], status)


def _usage_error(msg: str) -> NoReturn:
    """Emit a usage error per AGENT.md §4a (render_error → stderr, exit 2).

    Declared ``NoReturn`` so the type checker treats call sites as terminating.
    """
    render_error(msg)
    raise typer.Exit(2)


def _normalise_status(status: Any) -> dict[str, Any]:
    """Convert ClickUp status shapes into a stable JSON/table dict."""
    if isinstance(status, dict):
        return {
            "status": status.get("status"),
            "type": status.get("type"),
            "color": status.get("color"),
            "orderindex": status.get("orderindex"),
        }
    return {
        "status": getattr(status, "status", str(status)),
        "type": getattr(status, "type", None),
        "color": getattr(status, "color", None),
        "orderindex": getattr(status, "orderindex", None),
    }


def _statuses_from_list(list_obj: Any) -> list[dict[str, Any]]:
    """Extract allowed statuses from list metadata returned by ClickUp."""
    raw_statuses = (getattr(list_obj, "model_extra", None) or {}).get("statuses")
    if isinstance(raw_statuses, list):
        return [_normalise_status(status) for status in raw_statuses]
    list_status = getattr(list_obj, "status", None)
    if list_status is not None:
        return [_normalise_status(list_status)]
    return []


@app.command("statuses")
def list_task_statuses(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID or alias to inspect"),
) -> None:
    """Show statuses available for a ClickUp list."""

    async def _list_task_statuses() -> None:
        list_id_to_use = _resolve_list_id(list_id)
        if not list_id_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                list_obj = await client.get_list(list_id_to_use)
                statuses = _statuses_from_list(list_obj)
                render_statuses(statuses, list_id=list_obj.id, list_name=list_obj.name)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_list_task_statuses())


# Default status names for the short verb aliases. Intentionally raw strings,
# not `TaskStatusEnum` values — that enum captures ClickUp's built-in API
# statuses (open/in_progress/review/closed), but most real lists use custom
# status names. These defaults match the common convention; users on lists
# with different names override per-call with `--status STR`.
_DONE_STATUS = "complete"
_START_STATUS = "in progress"
_PARK_STATUS = "on-deck"


@app.command("status")
def change_status(
    task_id_arg: str | None = typer.Argument(None, metavar="TASK_ID", help="Task ID (positional)"),
    status_arg: str | None = typer.Argument(None, metavar="STATUS", help="New status (positional)"),
    task_id_flag: str | None = typer.Option(None, "--task-id", "-t", help="Task ID (back-compat alias for positional)"),
    task_ids_flag: str | None = typer.Option(None, "--task-ids", help="Comma-separated task IDs"),
    status_flag: str | None = typer.Option(
        None, "--status", "-s", help="New status (back-compat alias for positional)"
    ),
) -> None:
    """Change task status.

    Positional form: clickup task status TASK_ID STATUS
    Flag form (back-compat): clickup task status --task-id TASK_ID --status STATUS

    Mixing positional + flag for the same parameter is rejected (exit 2) so
    agents don't silently get one value when they thought they passed two.
    """
    if task_id_arg is not None and task_id_flag is not None:
        _usage_error("Error: pass TASK_ID either as a positional argument OR via --task-id, not both.")
    if task_ids_flag is not None and (task_id_arg is not None or task_id_flag is not None):
        _usage_error("Error: pass TASK_ID either as a single task ID OR via --task-ids, not both.")
    if status_arg is not None and status_flag is not None:
        _usage_error("Error: pass STATUS either as a positional argument OR via --status, not both.")

    task_id = task_id_arg or task_id_flag
    task_ids = _split_csv(task_ids_flag) if task_ids_flag is not None else ([task_id] if task_id else [])
    status = status_arg or status_flag

    if not task_ids:
        _usage_error("Error: Task ID is required, or pass --task-ids. Usage: clickup task status TASK_ID STATUS")
    if not status:
        _usage_error("Error: Status is required. Usage: clickup task status TASK_ID STATUS")

    # Type-narrow for the type checker; the _usage_error calls above raise on None.
    assert status is not None
    run_async(_do_status_change_many(task_ids, status))


@app.command("done")
def task_done(
    task_id: str = typer.Argument(..., help="Task ID"),
    status: str = typer.Option(_DONE_STATUS, "--status", "-s", help=f"Target status name (default: '{_DONE_STATUS}')"),
) -> None:
    """Close a task. Sets status to 'complete' unless --status overrides."""
    run_async(_do_status_change(task_id, status))


@app.command("close")
def task_close(
    task_id: str = typer.Argument(..., help="Task ID"),
    status: str = typer.Option(_DONE_STATUS, "--status", "-s", help=f"Target status name (default: '{_DONE_STATUS}')"),
) -> None:
    """Close a task. Alias for `task done`."""
    task_done(task_id=task_id, status=status)


@app.command("start")
def task_start(
    task_id: str = typer.Argument(..., help="Task ID"),
    status: str = typer.Option(
        _START_STATUS, "--status", "-s", help=f"Target status name (default: '{_START_STATUS}')"
    ),
) -> None:
    """Move a task to 'in progress' unless --status overrides."""
    run_async(_do_status_change(task_id, status))


@app.command("park")
def task_park(
    task_id: str = typer.Argument(..., help="Task ID"),
    status: str = typer.Option(_PARK_STATUS, "--status", "-s", help=f"Target status name (default: '{_PARK_STATUS}')"),
) -> None:
    """Park a task on the on-deck queue unless --status overrides."""
    run_async(_do_status_change(task_id, status))


@app.command("delete")
def delete_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to confirm deletion. No interactive prompt.",
    ),
) -> None:
    """Delete a task."""

    async def _delete_task() -> None:
        if not force:
            render_error("Refusing to delete without --force/--yes (this CLI never prompts).")
            raise typer.Exit(2)

        try:
            async with await get_client() as client:
                await client.delete_task(task_id)
                if get_format() == "json":
                    render_kv({"id": task_id, "deleted": True})
                    return
                render_message(f"Deleted task {task_id}", "success")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_delete_task())


@app.command("search")
def search_tasks(
    query: str | None = typer.Option(None, "--query", "-q", help="Search query"),
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID to search in"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
) -> None:
    """Search for tasks across the workspace.

    ClickUp search performs fuzzy/full-text matching across multiple task
    fields (name, description, comments, custom fields, etc.), not just the
    task name. Results are ranked by relevance.
    """

    async def _search_tasks() -> None:
        if not query:
            render_error("Error: Search query is required.")
            console.print("Use --query to specify the search terms")
            raise typer.Exit(1)

        # Use either workspace_id or team_id (they're the same thing)
        id_to_use = workspace_id or team_id
        if not id_to_use:
            config = Config()
            id_to_use = config.get("default_team_id")
        if not id_to_use:
            render_error("Error: Workspace ID is required for search.")
            console.print("Use --workspace-id or --team-id, or set default_team_id in config")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                tasks = await client.search_tasks(id_to_use, query)
                if not tasks:
                    render_message(f"No tasks found matching '{query}'", "warn")
                    return

                render_tasks(tasks)
                render_message(f"\nFound {len(tasks)} task(s)", "info")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_search_tasks())


@app.command("export")
def export_tasks(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to export tasks from"),
    output_file: str = typer.Option("tasks.json", "--output", "-o", help="Output file path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format (json, csv)"),
    include_completed: bool = typer.Option(True, "--include-completed", help="Include completed tasks"),
) -> None:
    """Export tasks from a list to a file."""

    async def _export_tasks() -> None:
        list_id_to_use = _resolve_list_id(list_id)

        if not list_id_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                filters: dict[str, Any] = {}
                if not include_completed:
                    filters["include_closed"] = False

                tasks = await client.get_tasks(list_id_to_use, **filters)
                if format.lower() == "json":
                    import json

                    task_data = []
                    for task in tasks:
                        task_dict = task.model_dump()
                        # Simplify complex fields for JSON export
                        if task_dict.get("status"):
                            task_dict["status"] = task_dict["status"].get("status", "")
                        if task_dict.get("priority"):
                            task_dict["priority"] = task_dict["priority"].get("priority", "")
                        if task_dict.get("assignees"):
                            task_dict["assignees"] = [a.get("username", "") for a in task_dict["assignees"]]
                        task_data.append(task_dict)

                    with open(output_file, "w", encoding="utf-8") as jsonfile:
                        json.dump(task_data, jsonfile, indent=2, ensure_ascii=False)

                elif format.lower() == "csv":
                    import csv

                    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
                        fieldnames = ["id", "name", "status", "priority", "assignees", "due_date", "description"]
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()

                        for task in tasks:
                            t_status = task.status.status if task.status else ""
                            t_priority = task.priority.priority or "" if task.priority else ""
                            assignees = ", ".join([a.username for a in task.assignees]) if task.assignees else ""

                            writer.writerow(
                                {
                                    "id": task.id,
                                    "name": task.name,
                                    "status": t_status,
                                    "priority": t_priority,
                                    "assignees": assignees,
                                    "due_date": task.due_date or "",
                                    "description": task.description or "",
                                }
                            )
                else:
                    render_error(f"Unsupported format: {format}")
                    raise typer.Exit(1)

                render_message(f"Exported {len(tasks)} tasks to {output_file}", "success")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_export_tasks())


# --- Comments subcommands ---


@comments_app.command("list")
def list_comments(
    task_id: str = typer.Argument(..., help="Task ID to list comments for"),
) -> None:
    """List all comments on a task."""

    async def _list_comments() -> None:
        try:
            async with await get_client() as client:
                comments = await client.get_task_comments(task_id)
                if not comments:
                    render_message(f"No comments on task {task_id}.", "warn")
                    return

                render_comments(comments)
                render_message(f"\n{len(comments)} comment(s)", "info")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_list_comments())


@comments_app.command("add")
def add_comment(
    task_id: str = typer.Argument(..., help="Task ID to comment on"),
    text: str = typer.Argument(..., help="Comment text"),
) -> None:
    """Add a comment to a task."""

    async def _add_comment() -> None:
        try:
            async with await get_client() as client:
                comment = await client.create_comment(task_id, text)
                if get_format() == "json":
                    render_comment(comment)
                    return
                render_message(f"Comment added (ID: {comment.id})", "success")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_add_comment())
