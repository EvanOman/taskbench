"""List management commands."""

from typing import Any

import typer
from rich.console import Console

from ...core import ClickUpClient, ClickUpError, Config
from ..output import render_error, render_list, render_lists
from ..utils import run_async

app = typer.Typer(help="List management")
console = Console()


async def get_client() -> ClickUpClient:
    """Get configured ClickUp client."""
    config = Config()
    if not config.has_credentials():
        console.print(
            "[red]Error: No ClickUp API token configured. Set CLICKUP_API_KEY in your "
            "environment (or .env), or run 'clickup config set-token <token>'.[/red]"
        )
        raise typer.Exit(1)
    return ClickUpClient(config, console)


def _resolve_list_id(list_id: str | None) -> str | None:
    """Resolve a list ID, expanding configured aliases (mirrors task.py)."""
    config = Config()
    resolver = getattr(config, "resolve_list_id", None)
    if callable(resolver):
        result: str | None = resolver(list_id)
        return result
    return list_id or config.get("default_list_id")


@app.command("show")
def list_lists(
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID"),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID (for folderless lists)"),
) -> None:
    """List all lists in a folder or space."""

    async def _list_lists() -> None:
        if not folder_id and not space_id:
            render_error("Error: Either folder ID or space ID is required.")
            console.print("Use --folder-id for lists in a folder or --space-id for folderless lists")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                if folder_id:
                    lists = await client.get_lists(folder_id)
                else:
                    # space_id is guaranteed non-None here due to the check above
                    assert space_id is not None
                    lists = await client.get_folderless_lists(space_id)
                render_lists(lists)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_list_lists())


@app.command("get")
def get_list(list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID")) -> None:
    """Get detailed information about a specific list."""

    async def _get_list() -> None:
        list_id_to_use = _resolve_list_id(list_id)

        if not list_id_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                list_item = await client.get_list(list_id_to_use)
                render_list(list_item)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_get_list())


@app.command("create")
def create_list(
    name: str = typer.Argument(..., help="List name"),
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID to create list in"),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID to create folderless list in"),
    content: str | None = typer.Option(None, "--content", "-c", help="List description/content"),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
    priority: int | None = typer.Option(None, "--priority", help="Priority (1-4)"),
    assignee: str | None = typer.Option(None, "--assignee", help="Assignee user ID"),
) -> None:
    """Create a new list."""

    async def _create_list() -> None:
        if not folder_id and not space_id:
            render_error("Error: Either folder ID or space ID is required.")
            console.print("Use --folder-id to create list in a folder or --space-id for folderless list")
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
                console.print(f"✅ Created list: {list_item.name} (ID: {list_item.id})")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_create_list())
