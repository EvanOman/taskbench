"""Workspace management commands."""

import typer

from ...core import ClickUpError, Config
from ..output import render_error, render_folders, render_message, render_spaces, render_teams, render_users
from ..shared import get_client
from ..utils import run_async

app = typer.Typer(help="Workspace management")


@app.command("list")
def list_workspaces() -> None:
    """List all available workspaces/teams."""

    async def _list_workspaces() -> None:
        try:
            async with await get_client() as client:
                teams = await client.get_teams()
                if not teams:
                    render_message("No workspaces found.", "info")
                    return
                render_teams(teams)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from None
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"An unexpected error occurred: {e}")
            raise typer.Exit(1) from e

    run_async(_list_workspaces())


@app.command("spaces")
def list_spaces(
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    show_private: bool = typer.Option(False, "--show-private", help="Show privacy information"),
) -> None:
    """List spaces in a workspace."""

    async def _list_spaces() -> None:
        config = Config()
        workspace_id_to_use = workspace_id or team_id or config.get("default_team_id")

        if not workspace_id_to_use:
            render_error(
                "No workspace ID provided and no default workspace configured. "
                "Use --workspace-id or set a default with 'clickup config set default_team_id <id>'."
            )
            raise typer.Exit(2) from None

        try:
            async with await get_client() as client:
                spaces = await client.get_spaces(workspace_id_to_use)
                if not spaces:
                    render_message("No spaces found.", "info")
                    return
                render_spaces(spaces)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from None
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"An unexpected error occurred: {e}")
            raise typer.Exit(1) from e

    run_async(_list_spaces())


@app.command("folders")
def list_folders(
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID"),
    show_counts: bool = typer.Option(False, "--show-counts", help="Show task count information"),
) -> None:
    """List folders in a space."""

    async def _list_folders() -> None:
        config = Config()
        space_id_to_use = space_id or config.get("default_space_id")

        if not space_id_to_use:
            render_error(
                "No space ID provided and no default space configured. "
                "Use --space-id or set a default with 'clickup config set default_space_id <id>'."
            )
            raise typer.Exit(2) from None

        try:
            async with await get_client() as client:
                folders = await client.get_folders(space_id_to_use)
                if not folders:
                    render_message("No folders found.", "info")
                    return
                render_folders(folders)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from None
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"An unexpected error occurred: {e}")
            raise typer.Exit(1) from e

    run_async(_list_folders())


@app.command("members")
def list_members(
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    role: str | None = typer.Option(None, "--role", help="Filter by role"),
) -> None:
    """List members in a workspace."""

    async def _list_members() -> None:
        config = Config()
        workspace_id_to_use = workspace_id or team_id or config.get("default_team_id")

        if not workspace_id_to_use:
            render_error(
                "No workspace ID provided and no default workspace configured. "
                "Use --workspace-id or set a default with 'clickup config set default_team_id <id>'."
            )
            raise typer.Exit(2) from None

        try:
            async with await get_client() as client:
                members = await client.get_team_members(workspace_id_to_use)
                if not members:
                    render_message("No members found.", "info")
                    return
                render_users(members, title="Workspace Members")
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from None
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"An unexpected error occurred: {e}")
            raise typer.Exit(1) from e

    run_async(_list_members())
