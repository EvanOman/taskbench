"""Task management commands."""

from typing import Any

import typer

from ...core import ClickUpError, Config
from ..output import (
    _print_json,
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
from ..shared import (
    gather_bounded,
    get_client,
    handle_clickup_errors,
    require_list_id,
    resolve_list_ids,
    resolve_workspace_id,
    split_csv,
    usage_error,
)
from ..task_filters import (
    annotate_source_list,
    apply_task_filters,
    epoch_ms,
    parse_sort,
    set_exclusive_date_filter,
    statuses_from_list,
    validate_priority,
    validate_task_name,
)
from ..utils import run_async

app = typer.Typer(help="Task management")

# Subgroup for comments
comments_app = typer.Typer(help="Task comment operations")
app.add_typer(comments_app, name="comments")


@app.command("list")
def list_tasks(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to get tasks from"),
    all_lists: bool = typer.Option(
        False,
        "--all-lists",
        help=(
            "Query every list configured in the default_lists aliases — NOT every list in the "
            "workspace. Run 'clickup config get default_lists' to see what's configured. "
            "For a workspace-wide query use 'task search' or 'task mine'."
        ),
    ),
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
            "When direction is implicit, --reverse decides. "
            "Note: priority encodes 1=urgent..4=low numerically, so 'priority' (asc) "
            "puts urgent first; 'priority:desc' puts low first. Tasks missing the field always sort last."
        ),
    ),
    reverse: bool = typer.Option(
        False,
        "--reverse",
        help="Sort descending. Illegal when --sort already has an explicit direction.",
    ),
    open_only: bool = typer.Option(
        False,
        "--open-only",
        "--open",
        help="Hide tasks whose status type is 'closed' (e.g. 'complete'). Shorthand for the 'all-but-closed' query.",
    ),
    brief: bool = typer.Option(
        False,
        "--brief",
        help=(
            "Return only id/name/status/priority/assignees/due_date/url/list. "
            "Drops noisy null fields and flattens status to a string."
        ),
    ),
) -> None:
    """List tasks from a ClickUp list.

    Supports the same --status/--sort/--updated-since/--open-only filters
    as ``task mine`` and ``task search``.
    """
    order_by, descending = parse_sort(sort, reverse)

    async def _list_tasks() -> None:
        list_ids_to_use = resolve_list_ids(list_id, all_lists=all_lists)

        if not list_ids_to_use:
            usage_error(
                "Error: No list ID provided and no default list configured.",
                hint="Use --list-id or set a default with 'clickup config set default_list_id <id>'",
            )

        with handle_clickup_errors():
            async with await get_client() as client:
                filters: dict[str, Any] = {}
                if status:
                    filters["statuses"] = split_csv(status)
                if assignee:
                    filters["assignees"] = [assignee]
                # Sort is applied client-side after the merge so multi-list
                # queries get a global order, not a per-list-then-concat one.
                set_exclusive_date_filter(
                    filters,
                    "date_created_gt",
                    [("--created-since", created_since), ("--created-after", created_after)],
                )
                set_exclusive_date_filter(filters, "date_created_lt", [("--created-before", created_before)])
                set_exclusive_date_filter(
                    filters,
                    "date_updated_gt",
                    [("--updated-since", updated_since), ("--updated-after", updated_after)],
                )
                set_exclusive_date_filter(filters, "date_updated_lt", [("--updated-before", updated_before)])

                tasks = []
                include_source = len(list_ids_to_use) > 1
                for list_id_to_use in list_ids_to_use:
                    list_tasks_result = await client.get_tasks(list_id_to_use, **filters)
                    if include_source:
                        list_tasks_result = [annotate_source_list(task, list_id_to_use) for task in list_tasks_result]
                    tasks.extend(list_tasks_result)
                # Client-side filter + sort pipeline. open_only and sort are
                # applied here (status/date filters already went to the API).
                pre_filter_count = len(tasks)
                has_filters = any(
                    [
                        status,
                        assignee,
                        open_only,
                        created_since,
                        created_after,
                        created_before,
                        updated_since,
                        updated_after,
                        updated_before,
                    ]
                )
                tasks = apply_task_filters(
                    tasks,
                    open_only=open_only,
                    sort_field=order_by,
                    sort_descending=descending,
                )
                tasks = tasks[:limit]
                render_tasks(tasks, brief=brief)
                if not tasks:
                    if has_filters:
                        render_message(
                            f"0 tasks matched the active filters (list has {pre_filter_count} tasks total).",
                            "info",
                        )
                    else:
                        render_message("No tasks found.", "info")

    run_async(_list_tasks())


@app.command("get")
def get_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    brief: bool = typer.Option(
        False,
        "--brief",
        help=(
            "Return only id/name/status/priority/assignees/due_date/url/list. "
            "Drops noisy null fields and flattens status to a string."
        ),
    ),
) -> None:
    """Get detailed information about a specific task.

    Shows all available fields including tags, parent, custom fields,
    time estimate, time tracked, watchers, and list/folder/space context.
    With ``--brief`` the response is the agent-routing subset only.
    """

    async def _get_task() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                task = await client.get_task(task_id)
                render_task(task, brief=brief)

    run_async(_get_task())


@app.command("mine")
def my_tasks(
    workspace_id: str | None = typer.Option(
        None,
        "--workspace-id",
        "-w",
        help="Workspace/team ID (defaults to default_team_id or auto-detected single workspace)",
    ),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status; comma-separated values allowed"),
    updated_since: str | None = typer.Option(None, "--updated-since", help="Updated after relative time, e.g. 7d"),
    sort: str | None = typer.Option(
        None,
        "--sort",
        "--order-by",
        help=(
            "Sort by: created, updated, due_date, priority. Direction: 'priority:desc', '-priority', '+priority'. "
            "Priority is numeric (1=urgent..4=low), so 'priority' (asc) puts urgent first."
        ),
    ),
    reverse: bool = typer.Option(False, "--reverse", help="Sort descending."),
    limit: int = typer.Option(50, "--limit", help="Maximum number of tasks to show"),
    open_only: bool = typer.Option(
        False,
        "--open-only",
        "--open",
        help="Hide tasks whose status type is 'closed'.",
    ),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task list --brief`)."),
) -> None:
    """List tasks assigned to the authenticated user.

    Searches across the workspace for tasks assigned to you. Uses the default
    workspace from config, or auto-detects if you belong to exactly one workspace.

    Supports the same --status/--sort/--updated-since/--open-only filters
    as ``task list`` and ``task search``.
    """
    order_by, descending = parse_sort(sort, reverse)
    status_filter = {s.lower() for s in split_csv(status)} if status else None
    updated_since_ms = epoch_ms(updated_since) if updated_since else None

    async def _my_tasks() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                # Get the authenticated user's ID
                user = await client.get_user()
                ws_id = await resolve_workspace_id(client, workspace_id)

                # Search for tasks assigned to this user across the workspace
                # ClickUp API expects assignees[] as repeated query params
                tasks = await client.search_tasks(
                    ws_id,
                    "",
                    **{"assignees[]": [str(user.id)]},
                )

                # Client-side filter + sort via shared pipeline.
                pre_filter_count = len(tasks)
                has_filters = any([status_filter, updated_since_ms, open_only])
                tasks = apply_task_filters(
                    tasks,
                    statuses=status_filter,
                    updated_since_ms=updated_since_ms,
                    open_only=open_only,
                    sort_field=order_by,
                    sort_descending=descending,
                )
                tasks = tasks[:limit]
                render_tasks(tasks, brief=brief)
                if not tasks:
                    if has_filters:
                        render_message(
                            f"0 tasks matched the active filters ({pre_filter_count} tasks total).",
                            "info",
                        )
                    else:
                        render_message("No tasks assigned to you.", "info")
                else:
                    render_message(f"Showing {len(tasks)} task(s) assigned to {user.username}.", "info")

    run_async(_my_tasks())


@app.command("create")
def create_task(
    names: list[str] = typer.Argument(..., metavar="NAME...", help="One or more task names"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID or alias to create task in"),
    description: str | None = typer.Option(None, "--description", "-d", help="Task description"),
    priority: int | None = typer.Option(
        None,
        "--priority",
        "-p",
        help="Priority (1=urgent, 2=high, 3=normal, 4=low).",
    ),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Assignee user ID"),
    due_date: str | None = typer.Option(
        None, "--due-date", help="Due date (YYYY-MM-DD, ISO datetime, epoch ms, or relative like 7d)"
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Initial status (e.g. 'on-deck'). Falls back to config default_status, then list default.",
    ),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Create one or more tasks.

    Pass multiple names to create several tasks at once — all flags
    (--description, --priority, --status, etc.) apply to every task.
    Single-name invocations are byte-identical to the old behavior.
    """
    for task_name in names:
        validate_task_name(task_name)
    validate_priority(priority)

    async def _create_task() -> None:
        list_id_to_use = require_list_id(list_id)

        config = Config()
        status_to_use = status or config.get("default_status")

        with handle_clickup_errors():
            task_data: dict[str, Any] = {}

            if description is not None:
                task_data["description"] = description
            if priority is not None:
                task_data["priority"] = priority
            if assignee is not None:
                task_data["assignees"] = [assignee]
            if due_date is not None:
                task_data["due_date"] = str(epoch_ms(due_date))
            if status_to_use:
                task_data["status"] = status_to_use

            async with await get_client() as client:
                if len(names) == 1:
                    # Single task — byte-identical to old behavior.
                    task = await client.create_task(list_id_to_use, name=names[0], **task_data)
                    if get_format() == "json":
                        render_task(task, brief=brief)
                        return
                    render_message(f"Created task: {task.name} (ID: {task.id})", "success")
                    if task.url:
                        render_message(f"URL: {task.url}", "info")
                    return

                # Batch create — concurrent with partial-failure semantics.
                results = await gather_bounded(
                    [client.create_task(list_id_to_use, name=n, **task_data) for n in names],
                    limit=5,
                )
                succeeded: list[Any] = []
                failures: list[tuple[str, BaseException]] = []
                for task_name, result in zip(names, results, strict=False):
                    if isinstance(result, BaseException):
                        failures.append((task_name, result))
                    else:
                        succeeded.append(result)

                # Render successes preserving input order.
                ordered = [r for r in results if not isinstance(r, BaseException)]
                render_tasks(ordered, brief=brief)

                for task_name, exc in failures:
                    render_error(f"Failed to create task '{task_name}': {exc}", error_type=type(exc).__name__)

                if failures:
                    raise typer.Exit(1)

    run_async(_create_task())


@app.command("update")
def update_task(
    task_id: str | None = typer.Argument(None, help="Task ID"),
    task_ids: str | None = typer.Option(None, "--task-ids", help="Comma-separated task IDs to update"),
    name: str | None = typer.Option(None, "--name", "-n", help="New task name"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description (pass '' to clear)"),
    description_append: str | None = typer.Option(
        None,
        "--description-append",
        help=(
            "Append text to the existing description. The caller supplies any leading "
            "separator (e.g. ' — ', '\\n'). Mutually exclusive with --description."
        ),
    ),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    priority: int | None = typer.Option(
        None,
        "--priority",
        "-p",
        help="New priority (1=urgent, 2=high, 3=normal, 4=low).",
    ),
    due_date: str | None = typer.Option(
        None, "--due-date", help="New due date (YYYY-MM-DD, ISO datetime, epoch ms, or relative like 7d)"
    ),
    archived: bool | None = typer.Option(None, "--archived/--unarchived", help="Archive state"),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Update a task. Only fields you pass are changed; everything else stays the same."""
    validate_priority(priority)
    if name is not None:
        validate_task_name(name)
    if description is not None and description_append is not None:
        usage_error("Error: --description and --description-append are mutually exclusive.")

    async def _update_task() -> None:
        if task_id is not None and task_ids is not None:
            usage_error("Error: pass TASK_ID either as a positional argument OR via --task-ids, not both.")
        target_ids = [task_id] if task_id is not None else split_csv(task_ids)
        if not target_ids:
            usage_error("Error: Task ID or --task-ids is required.")

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
            updates["due_date"] = str(epoch_ms(due_date))
        if archived is not None:
            updates["archived"] = archived

        if not updates and description_append is None:
            render_message("No updates specified.", "warn")
            return

        with handle_clickup_errors():
            async with await get_client() as client:
                tasks = []
                if description_append is not None:
                    # --description-append needs a per-task read-modify-write,
                    # so we resolve each target's new description inline before
                    # update. Sequential because each read depends on current state.
                    for target_id in target_ids:
                        per_task_updates = dict(updates)
                        current = await client.get_task(target_id)
                        existing = current.description or ""
                        per_task_updates["description"] = existing + description_append
                        tasks.append(await client.update_task(target_id, **per_task_updates))
                elif len(target_ids) == 1:
                    tasks.append(await client.update_task(target_ids[0], **updates))
                else:
                    # Multiple IDs without description-append — bounded concurrency
                    results = await gather_bounded(
                        [client.update_task(tid, **updates) for tid in target_ids],
                        limit=5,
                    )
                    for result in results:
                        if isinstance(result, BaseException):
                            raise result
                        tasks.append(result)
                if get_format() == "json":
                    if len(tasks) == 1:
                        render_task(tasks[0], brief=brief)
                    else:
                        render_tasks(tasks, brief=brief)
                    return
                if len(tasks) == 1:
                    render_message(f"Updated task: {tasks[0].name} (ID: {tasks[0].id})", "success")
                else:
                    render_message(f"Updated {len(tasks)} tasks.", "success")

    run_async(_update_task())


async def _do_status_change_many(task_ids: list[str], status: str, *, brief: bool = False) -> None:
    """Shared implementation for `task status` and short verb aliases.

    Each task is attempted independently — one bad ID doesn't abort the rest
    of the batch. Successful updates are rendered as the usual data envelope
    on stdout; each failure emits a canonical error envelope on stderr.
    Exits 1 if any task failed, so agents can detect partial success by
    pairing the exit code with the stdout envelope's count.
    """
    succeeded: list[Any] = []
    failures: list[tuple[str, ClickUpError]] = []
    async with await get_client() as client:
        results = await gather_bounded(
            [client.update_task(task_id, status=status) for task_id in task_ids],
            limit=5,
        )
        for task_id, result in zip(task_ids, results, strict=False):
            if isinstance(result, ClickUpError):
                failures.append((task_id, result))
            elif isinstance(result, BaseException):
                failures.append((task_id, ClickUpError(str(result))))
            else:
                succeeded.append(result)

    if succeeded:
        if get_format() == "json":
            if len(task_ids) == 1:
                render_task(succeeded[0], brief=brief)
            else:
                render_tasks(succeeded, brief=brief)
        elif len(succeeded) == 1 and not failures:
            render_message(f"Updated task status: {succeeded[0].name} -> {status}", "success")
        else:
            render_message(f"Updated {len(succeeded)}/{len(task_ids)} task statuses -> {status}", "success")

    for task_id, exc in failures:
        render_error(f"ClickUp API Error ({task_id}): {exc}", error_type=type(exc).__name__)
    if failures:
        raise typer.Exit(1)


@app.command("statuses")
def list_task_statuses(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID or alias to inspect"),
) -> None:
    """Show statuses available for a ClickUp list."""

    async def _list_task_statuses() -> None:
        list_id_to_use = require_list_id(list_id)

        with handle_clickup_errors():
            async with await get_client() as client:
                list_obj = await client.get_list(list_id_to_use)
                statuses = statuses_from_list(list_obj)
                render_statuses(statuses, list_id=list_obj.id, list_name=list_obj.name)

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
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Change task status.

    Positional form: clickup task status TASK_ID STATUS
    Flag form (back-compat): clickup task status --task-id TASK_ID --status STATUS

    See valid status values for a list with: clickup task statuses --list-id <id>

    Mixing positional + flag for the same parameter is rejected (exit 2) so
    agents don't silently get one value when they thought they passed two.
    """
    if task_id_arg is not None and task_id_flag is not None:
        usage_error("Error: pass TASK_ID either as a positional argument OR via --task-id, not both.")
    if task_ids_flag is not None and (task_id_arg is not None or task_id_flag is not None):
        usage_error("Error: pass TASK_ID either as a single task ID OR via --task-ids, not both.")
    if status_arg is not None and status_flag is not None:
        usage_error("Error: pass STATUS either as a positional argument OR via --status, not both.")

    task_id = task_id_arg or task_id_flag
    task_ids = split_csv(task_ids_flag) if task_ids_flag is not None else ([task_id] if task_id else [])
    status = status_arg or status_flag

    if not task_ids:
        usage_error("Error: Task ID is required, or pass --task-ids. Usage: clickup task status TASK_ID STATUS")
    if not status:
        usage_error("Error: Status is required. Usage: clickup task status TASK_ID STATUS")

    # Type-narrow for the type checker; the _usage_error calls above raise on None.
    assert status is not None
    run_async(_do_status_change_many(task_ids, status, brief=brief))


@app.command("done")
def task_done(
    task_ids: list[str] = typer.Argument(..., metavar="TASK_ID...", help="One or more task IDs"),
    status: str = typer.Option(_DONE_STATUS, "--status", "-s", help=f"Target status name (default: '{_DONE_STATUS}')"),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Close one or more tasks. Sets status to 'complete' unless --status overrides."""
    run_async(_do_status_change_many(task_ids, status, brief=brief))


@app.command("close")
def task_close(
    task_ids: list[str] = typer.Argument(..., metavar="TASK_ID...", help="One or more task IDs"),
    status: str = typer.Option(_DONE_STATUS, "--status", "-s", help=f"Target status name (default: '{_DONE_STATUS}')"),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Close one or more tasks. Alias for `task done`."""
    run_async(_do_status_change_many(task_ids, status, brief=brief))


@app.command("start")
def task_start(
    task_ids: list[str] = typer.Argument(..., metavar="TASK_ID...", help="One or more task IDs"),
    status: str = typer.Option(
        _START_STATUS, "--status", "-s", help=f"Target status name (default: '{_START_STATUS}')"
    ),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Move one or more tasks to 'in progress' unless --status overrides."""
    run_async(_do_status_change_many(task_ids, status, brief=brief))


@app.command("park")
def task_park(
    task_ids: list[str] = typer.Argument(..., metavar="TASK_ID...", help="One or more task IDs"),
    status: str = typer.Option(_PARK_STATUS, "--status", "-s", help=f"Target status name (default: '{_PARK_STATUS}')"),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task get --brief`)."),
) -> None:
    """Park one or more tasks on the on-deck queue unless --status overrides."""
    run_async(_do_status_change_many(task_ids, status, brief=brief))


@app.command("delete")
def delete_task(
    task_ids_args: list[str] | None = typer.Argument(
        None,
        metavar="TASK_ID...",
        help="One or more task IDs to delete",
    ),
    task_ids: str | None = typer.Option(None, "--task-ids", help="Comma-separated task IDs to delete (back-compat)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to confirm deletion. No interactive prompt.",
    ),
) -> None:
    """Delete one or more tasks.

    Positional form: clickup task delete ID1 ID2 ID3 --force
    Flag form (back-compat): clickup task delete --task-ids ID1,ID2 --force
    """

    async def _delete_task() -> None:
        has_positional = bool(task_ids_args)
        has_flag = task_ids is not None
        if has_positional and has_flag:
            usage_error("Error: pass TASK_ID either as positional arguments OR via --task-ids, not both.")
        target_ids = list(task_ids_args or []) if has_positional else split_csv(task_ids)
        if not target_ids:
            usage_error("Error: Task ID or --task-ids is required.")

        if not force:
            render_error("Refusing to delete without --force/--yes (this CLI never prompts).", error_type="UsageError")
            raise typer.Exit(2)

        succeeded: list[dict[str, object]] = []
        failures: list[tuple[str, Exception]] = []
        async with await get_client() as client:
            results = await gather_bounded(
                [client.delete_task(tid) for tid in target_ids],
                limit=5,
            )
            for tid, result in zip(target_ids, results, strict=False):
                if isinstance(result, BaseException):
                    exc = result if isinstance(result, ClickUpError) else ClickUpError(str(result))
                    failures.append((tid, exc))
                    render_message(f"Failed to delete task {tid}: {result}", "warn")
                else:
                    succeeded.append({"id": tid, "deleted": True})

        if get_format() == "json":
            if len(target_ids) == 1 and not failures:
                render_kv({"id": target_ids[0], "deleted": True})
            else:
                results = list(succeeded) + [{"id": tid, "deleted": False} for tid, _ in failures]
                _print_json({"data": results, "count": len(results)})
        else:
            if succeeded and not failures:
                if len(succeeded) == 1:
                    render_message(f"Deleted task {succeeded[0]['id']}", "success")
                else:
                    render_message(f"Deleted {len(succeeded)} tasks.", "success")
            elif succeeded:
                render_message(f"Deleted {len(succeeded)}/{len(target_ids)} tasks ({len(failures)} failed).", "warn")

        for tid, exc in failures:
            render_error(f"ClickUp API Error ({tid}): {exc}", error_type=type(exc).__name__)
        if failures:
            raise typer.Exit(1)

    run_async(_delete_task())


@app.command("search")
def search_tasks(
    query: str | None = typer.Option(
        None,
        "--query",
        "-q",
        help="Search query. Omit for workspace-wide enumeration (returns all tasks).",
    ),
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID to search in"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status; comma-separated values allowed"),
    sort: str | None = typer.Option(
        None,
        "--sort",
        "--order-by",
        help=(
            "Sort by: created, updated, due_date, priority. Direction: 'priority:desc', '-priority', '+priority'. "
            "Priority is numeric (1=urgent..4=low), so 'priority' (asc) puts urgent first."
        ),
    ),
    reverse: bool = typer.Option(False, "--reverse", help="Sort descending."),
    updated_since: str | None = typer.Option(None, "--updated-since", help="Updated after relative time, e.g. 7d"),
    open_only: bool = typer.Option(
        False,
        "--open-only",
        "--open",
        help="Hide tasks whose status type is 'closed'.",
    ),
    limit: int = typer.Option(50, "--limit", help="Maximum number of tasks to show"),
    name_only: bool = typer.Option(
        False,
        "--name-only",
        help=(
            "Keep only tasks whose NAME contains the query "
            "(ClickUp's search is full-text across descriptions/comments)."
        ),
    ),
    brief: bool = typer.Option(False, "--brief", help="Return a stripped projection (see `task list --brief`)."),
) -> None:
    """Search for tasks across the workspace.

    ClickUp search performs fuzzy/full-text matching across multiple task
    fields (name, description, comments, custom fields, etc.), not just the
    task name. Results are ranked by relevance. Omit --query for a bare
    workspace-wide enumeration (all tasks).

    Supports the same --status/--sort/--updated-since/--open-only filters
    as ``task list`` and ``task mine``.
    """
    order_by, descending = parse_sort(sort, reverse)
    status_filter = {s.lower() for s in split_csv(status)} if status else None
    updated_since_ms = epoch_ms(updated_since) if updated_since else None

    async def _search_tasks() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                id_to_use = await resolve_workspace_id(client, workspace_id or team_id)
                tasks = await client.search_tasks(id_to_use, query or "")
                pre_filter_count = len(tasks)
                has_filters = any([status_filter, updated_since_ms, open_only, query, name_only])
                # Client-side filter + sort via shared pipeline.
                tasks = apply_task_filters(
                    tasks,
                    statuses=status_filter,
                    updated_since_ms=updated_since_ms,
                    open_only=open_only,
                    sort_field=order_by,
                    sort_descending=descending,
                )
                if name_only and query:
                    query_lower = query.lower()
                    tasks = [t for t in tasks if query_lower in t.name.lower()]
                tasks = tasks[:limit]
                render_tasks(tasks, brief=brief)
                if not tasks:
                    if has_filters:
                        render_message(
                            f"0 tasks matched the active filters ({pre_filter_count} tasks total).",
                            "info",
                        )
                    elif query:
                        render_message(f"No tasks found matching '{query}'", "info")
                    else:
                        render_message("No tasks found.", "info")
                else:
                    render_message(f"Found {len(tasks)} task(s)", "info")

    run_async(_search_tasks())


@app.command("export")
def export_tasks(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to export tasks from"),
    output_file: str = typer.Option("tasks.json", "--output", "-o", help="Output file path"),
    output_format: str = typer.Option("json", "--output-format", help="Output format (json, csv)"),
    include_completed: bool = typer.Option(True, "--include-completed", help="Include completed tasks"),
) -> None:
    """Export tasks from a list to a file."""

    async def _export_tasks() -> None:
        list_id_to_use = require_list_id(list_id)

        with handle_clickup_errors():
            async with await get_client() as client:
                filters: dict[str, Any] = {}
                if not include_completed:
                    filters["include_closed"] = False

                tasks = await client.get_tasks(list_id_to_use, **filters)
                if output_format.lower() == "json":
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

                elif output_format.lower() == "csv":
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
                    render_error(f"Unsupported format: {output_format}")
                    raise typer.Exit(1)

                render_kv({"exported": len(tasks), "output_file": output_file, "format": output_format.lower()})

    run_async(_export_tasks())


# --- Comments subcommands ---


@comments_app.command("list")
def list_comments(
    task_id: str = typer.Argument(..., help="Task ID to list comments for"),
) -> None:
    """List all comments on a task."""

    async def _list_comments() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                comments = await client.get_task_comments(task_id)
                render_comments(comments)
                if not comments:
                    render_message(f"No comments on task {task_id}.", "info")
                else:
                    render_message(f"{len(comments)} comment(s)", "info")

    run_async(_list_comments())


@comments_app.command("add")
def add_comment(
    task_id: str = typer.Argument(..., help="Task ID to comment on"),
    text: str = typer.Argument(..., help="Comment text"),
) -> None:
    """Add a comment to a task."""

    async def _add_comment() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                comment = await client.create_comment(task_id, text)
                if get_format() == "json":
                    render_comment(comment)
                    return
                render_message(f"Comment added (ID: {comment.id})", "success")

    run_async(_add_comment())
