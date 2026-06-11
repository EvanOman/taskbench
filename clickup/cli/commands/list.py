"""List management commands."""

from typing import Any

import typer
from rich.console import Console

from ...core import ClickUpError, Config, TaskProvider, get_provider, provider_requires_credentials
from ..output import render_error, render_list, render_lists, render_message
from ..utils import run_async

app = typer.Typer(help="List management")
console = Console()


async def get_client() -> TaskProvider:
    """Get configured task provider."""
    config = Config()
    if provider_requires_credentials(config) and not config.has_credentials():
        render_error(
            "No ClickUp API token configured.",
            hint="Set CLICKUP_API_KEY in your environment (or .env), or run 'clickup config set-token <token>'.",
        )
        raise typer.Exit(1)
    return get_provider(config, console)


def _resolve_list_id(list_id: str | None) -> str | None:
    """Resolve a list ID, expanding configured aliases (mirrors task.py)."""
    return Config().resolve_list_id(list_id)


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

        try:
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

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

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
        list_id_to_use = _resolve_list_id(list_id_arg or list_id)

        if not list_id_to_use:
            render_error(
                "Error: No list ID provided and no default list configured.",
                hint="Use --list-id or set a default with 'clickup config set default_list_id <id>'",
            )
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                list_item = await client.get_list(list_id_to_use)
                render_list(list_item, brief=brief)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

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

        try:
            list_data: dict[str, Any] = {"name": name}

            if content:
                list_data["content"] = content
            if due_date:
                list_data["due_date"] = due_date
            if priority:
                list_data["priority"] = priority
            if assignee:
                list_data["assignee"] = assignee

            async with await get_client() as client:
                if folder_id:
                    list_item = await client.create_list(folder_id, **list_data)
                else:
                    # space_id is guaranteed non-None here due to the check above
                    assert space_id is not None
                    list_item = await client.create_folderless_list(space_id, **list_data)
                render_list(list_item)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

    run_async(_create_list())
