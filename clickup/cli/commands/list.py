"""List management commands."""

from typing import Any

import typer

from ..output import format_timestamp, render_error, render_list, render_list_stats, render_lists, render_message
from ..shared import gather_bounded, get_client, handle_clickup_errors, require_list_id, resolve_workspace_id
from ..task_filters import filter_open_only
from ..utils import run_async

app = typer.Typer(help="List management")


@app.command("show")
def list_lists(
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID"),
    space_id: str | None = typer.Option(
        None,
        "--space-id",
        "-s",
        help=(
            "Space ID (returns only folderless lists — the ClickUp API does not include lists "
            "inside folders here). Use --folder-id to get lists within a specific folder, or "
            "'discover hierarchy' to see the full tree."
        ),
    ),
) -> None:
    """List all lists in a folder or space."""

    async def _list_lists() -> None:
        if not folder_id and not space_id:
            render_error(
                "Error: Either folder ID or space ID is required.",
                hint="Use --folder-id for lists in a folder or --space-id for folderless lists",
            )
            raise typer.Exit(1)

        with handle_clickup_errors():
            async with await get_client() as client:
                if folder_id:
                    lists = await client.get_lists(folder_id)
                else:
                    # space_id is guaranteed non-None here due to the check above
                    assert space_id is not None
                    lists = await client.get_folderless_lists(space_id)
                    render_message(
                        "Note: --space-id returns only folderless lists. Lists inside folders "
                        "are not included. Use 'discover hierarchy' to see the full tree.",
                        level="info",
                    )
                render_lists(lists)

    run_async(_list_lists())


@app.command("list")
def list_lists_alias(
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID"),
    space_id: str | None = typer.Option(
        None,
        "--space-id",
        "-s",
        help=(
            "Space ID (returns only folderless lists — the ClickUp API does not include lists "
            "inside folders here). Use --folder-id to get lists within a specific folder, or "
            "'discover hierarchy' to see the full tree."
        ),
    ),
) -> None:
    """List all lists in a folder or space. Alias for `list show`."""
    list_lists(folder_id=folder_id, space_id=space_id)


@app.command("ls")
def list_lists_ls(
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID"),
    space_id: str | None = typer.Option(
        None,
        "--space-id",
        "-s",
        help=(
            "Space ID (returns only folderless lists — the ClickUp API does not include lists "
            "inside folders here). Use --folder-id to get lists within a specific folder, or "
            "'discover hierarchy' to see the full tree."
        ),
    ),
) -> None:
    """List all lists in a folder or space. Alias for `list show`."""
    list_lists(folder_id=folder_id, space_id=space_id)


@app.command("get")
def get_list(
    list_id_arg: str | None = typer.Argument(None, metavar="LIST_ID", help="List ID or alias (positional)"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID (back-compat alias for positional)"),
    brief: bool = typer.Option(
        False,
        "--brief",
        help="Return only id/name/task_count/folder/space.",
    ),
) -> None:
    """Get detailed information about a specific list.

    Positional form: clickup list get LIST_ID (matches `task get TASK_ID`).
    Flag form (back-compat): clickup list get --list-id LIST_ID
    """
    if list_id_arg is not None and list_id is not None:
        render_error("Error: pass LIST_ID either as a positional argument OR via --list-id, not both.")
        raise typer.Exit(2)

    async def _get_list() -> None:
        list_id_to_use = require_list_id(list_id_arg or list_id)

        with handle_clickup_errors():
            async with await get_client() as client:
                list_item = await client.get_list(list_id_to_use)
                render_list(list_item, brief=brief)

    run_async(_get_list())


@app.command("create")
def create_list(
    name: str = typer.Argument(..., help="List name"),
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID to create list in"),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID to create folderless list in"),
    content: str | None = typer.Option(None, "--content", "-c", help="List description/content"),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
    priority: int | None = typer.Option(None, "--priority", help="Priority (1=urgent, 2=high, 3=normal, 4=low)."),
    assignee: str | None = typer.Option(None, "--assignee", help="Assignee user ID"),
) -> None:
    """Create a new list."""

    async def _create_list() -> None:
        if not folder_id and not space_id:
            render_error(
                "Error: Either folder ID or space ID is required.",
                hint="Use --folder-id to create list in a folder or --space-id for folderless list",
            )
            raise typer.Exit(1)

        with handle_clickup_errors():
            list_data: dict[str, Any] = {"name": name}

            if content is not None:
                list_data["content"] = content
            if due_date is not None:
                list_data["due_date"] = due_date
            if priority is not None:
                list_data["priority"] = priority
            if assignee is not None:
                list_data["assignee"] = assignee

            async with await get_client() as client:
                if folder_id:
                    list_item = await client.create_list(folder_id, **list_data)
                else:
                    # space_id is guaranteed non-None here due to the check above
                    assert space_id is not None
                    list_item = await client.create_folderless_list(space_id, **list_data)
                render_list(list_item)

    run_async(_create_list())


@app.command("stats")
def list_stats(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", "-w", help="Workspace ID (auto-detected if only one)."
    ),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Limit to a single space."),
    sort: str = typer.Option(
        "updated", "--sort", help="Sort order: 'tasks' (highest count first) or 'updated' (most recent first)."
    ),
) -> None:
    """Show per-list statistics: task count, open count, and last updated.

    Enumerates every list in the workspace (folders + folderless) and
    fetches tasks to compute stats. Use --space-id to limit scope.
    """

    async def _stats() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                # Collect all lists across spaces
                if space_id:
                    space_ids = [space_id]
                else:
                    ws_id = await resolve_workspace_id(client, workspace_id)
                    spaces = await client.get_spaces(ws_id)
                    space_ids = [s.id for s in spaces]

                all_lists: list[tuple[str, Any]] = []
                for sid in space_ids:
                    # Resolve space name
                    sp_name = sid
                    try:
                        sp = await client.get_space(sid)
                        sp_name = sp.name
                    except Exception:
                        pass

                    # Folderless lists
                    try:
                        folderless = await client.get_folderless_lists(sid)
                        for lst in folderless:
                            all_lists.append((sp_name, lst))
                    except Exception:
                        pass

                    # Folder lists
                    try:
                        folders = await client.get_folders(sid)
                        for folder in folders:
                            try:
                                folder_lists = await client.get_lists(folder.id)
                                for lst in folder_lists:
                                    all_lists.append((sp_name, lst))
                            except Exception:
                                pass
                    except Exception:
                        pass

                if not all_lists:
                    render_list_stats([])
                    return

                # Fetch tasks for each list (bounded concurrency)
                async def _fetch_tasks(list_id: str) -> list[Any]:
                    return await client.get_tasks(list_id, include_closed=True)

                task_results = await gather_bounded(
                    [_fetch_tasks(lst.id) for _, lst in all_lists],
                    limit=5,
                )

                rows: list[dict[str, Any]] = []
                for (sp_name, lst), tasks_or_exc in zip(all_lists, task_results, strict=True):
                    if isinstance(tasks_or_exc, Exception):
                        tasks = []
                    else:
                        tasks = tasks_or_exc

                    task_count = len(tasks) if tasks else (lst.task_count or 0)
                    open_count = len(filter_open_only(tasks)) if tasks else 0

                    # Find most recent date_updated
                    last_updated: str | None = None
                    if tasks:
                        max_ts: int | None = None
                        for t in tasks:
                            if t.date_updated:
                                try:
                                    ts = int(t.date_updated)
                                    if max_ts is None or ts > max_ts:
                                        max_ts = ts
                                except (TypeError, ValueError):
                                    pass
                        if max_ts is not None:
                            last_updated = format_timestamp(str(max_ts), for_json=True)

                    rows.append(
                        {
                            "id": lst.id,
                            "name": lst.name,
                            "space": sp_name,
                            "task_count": task_count,
                            "open_count": open_count,
                            "last_updated": last_updated,
                        }
                    )

                # Sort
                if sort == "tasks":
                    rows.sort(key=lambda r: r["task_count"], reverse=True)
                else:
                    # updated: most recent first; None sorts last
                    rows.sort(
                        key=lambda r: r["last_updated"] or "",
                        reverse=True,
                    )

                render_list_stats(rows)

    run_async(_stats())
