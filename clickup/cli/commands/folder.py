"""Folder management commands."""

import typer
from rich.console import Console

from ...core import ClickUpError, Config, TaskProvider, get_provider, provider_requires_credentials
from ..output import render_error, render_folder, render_folders
from ..utils import run_async

app = typer.Typer(help="Folder management")
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


def _resolve_space_id(space_id: str | None) -> str | None:
    """Resolve a space ID from the flag or the configured default."""
    return space_id or Config().get("default_space_id")


@app.command("list")
def list_folders(
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID (defaults to default_space_id)"),
) -> None:
    """List folders in a space."""

    async def _list_folders() -> None:
        space_id_to_use = _resolve_space_id(space_id)
        if not space_id_to_use:
            render_error(
                "Error: No space ID provided and no default space configured.",
                hint="Use --space-id or set a default with 'clickup config set default_space_id <id>'",
            )
            raise typer.Exit(2)
        try:
            async with await get_client() as client:
                folders = await client.get_folders(space_id_to_use)
                render_folders(folders)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

    run_async(_list_folders())


@app.command("get")
def get_folder(
    folder_id: str = typer.Argument(..., help="Folder ID"),
    brief: bool = typer.Option(
        False,
        "--brief",
        help="Return only id/name/task_count/hidden/space.",
    ),
) -> None:
    """Get detailed information about a specific folder."""

    async def _get_folder() -> None:
        try:
            async with await get_client() as client:
                folder = await client.get_folder(folder_id)
                render_folder(folder, brief=brief)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

    run_async(_get_folder())


@app.command("create")
def create_folder(
    name: str = typer.Argument(..., help="Folder name"),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID (defaults to default_space_id)"),
) -> None:
    """Create a new folder in a space."""

    async def _create_folder() -> None:
        space_id_to_use = _resolve_space_id(space_id)
        if not space_id_to_use:
            render_error(
                "Error: No space ID provided and no default space configured.",
                hint="Use --space-id or set a default with 'clickup config set default_space_id <id>'",
            )
            raise typer.Exit(2)
        try:
            async with await get_client() as client:
                folder = await client.create_folder(space_id_to_use, name)
                render_folder(folder)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

    run_async(_create_folder())
