"""Discovery commands for navigating ClickUp hierarchy."""

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from ...core import ClickUpClient, ClickUpError, Config
from ..output import render_error
from ..utils import Progress, SpinnerColumn, TextColumn, run_async

app = typer.Typer(help="Discover and navigate ClickUp hierarchy")
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


@app.command("hierarchy")
def show_hierarchy(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", "-w", help="Workspace ID (will list all if not provided)"
    ),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to explore"),
) -> None:
    """Show the complete ClickUp hierarchy tree."""

    async def _show_hierarchy() -> None:
        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Building hierarchy...", total=None)

                    tree = Tree("🏢 ClickUp Hierarchy")

                    # Use either workspace_id or team_id (they're the same thing)
                    id_to_use = workspace_id or team_id

                    if id_to_use:
                        workspaces = [await client.get_team(id_to_use)]
                    else:
                        workspaces = await client.get_teams()

                    for workspace in workspaces:
                        workspace_node = tree.add(
                            f"🏢 [bold cyan]{workspace.name}[/bold cyan] ([dim]{workspace.id}[/dim])"
                        )

                        if max_depth >= 2:
                            try:
                                spaces = await client.get_spaces(workspace.id)
                                for space in spaces:
                                    space_node = workspace_node.add(
                                        f"📁 [blue]{space.name}[/blue] ([dim]{space.id}[/dim])"
                                    )

                                    if max_depth >= 3:
                                        # Get folders in space
                                        try:
                                            folders = await client.get_folders(space.id)
                                            for folder in folders:
                                                folder_node = space_node.add(
                                                    f"📂 [yellow]{folder.name}[/yellow] ([dim]{folder.id}[/dim])"
                                                )

                                                if max_depth >= 4:
                                                    # Get lists in folder
                                                    try:
                                                        lists = await client.get_lists(folder.id)
                                                        for lst in lists:
                                                            folder_node.add(
                                                                f"📋 [green]{lst.name}[/green] ([dim]{lst.id}[/dim]) - "
                                                                f"{lst.task_count} tasks"
                                                            )
                                                    except ClickUpError:
                                                        pass
                                        except ClickUpError:
                                            pass

                                        # Get folderless lists in space
                                        try:
                                            folderless_lists = await client.get_folderless_lists(space.id)
                                            if folderless_lists:
                                                folderless_node = space_node.add("📂 [yellow]Folderless Lists[/yellow]")
                                                for lst in folderless_lists:
                                                    folderless_node.add(
                                                        f"📋 [green]{lst.name}[/green] ([dim]{lst.id}[/dim]) - "
                                                        f"{lst.task_count} tasks"
                                                    )
                                        except ClickUpError:
                                            pass
                            except ClickUpError as e:
                                workspace_node.add(f"❌ [red]Error loading spaces: {e}[/red]")

                    console.print(tree)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_show_hierarchy())


@app.command("ids")
def show_ids(
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    space_id: str | None = typer.Option(None, "--space-id", "-s", help="Space ID"),
    folder_id: str | None = typer.Option(None, "--folder-id", "-f", help="Folder ID"),
) -> None:
    """Show IDs for easy copy-paste. Use --folder-id to get list IDs."""

    async def _show_ids() -> None:
        try:
            async with await get_client() as client:
                if folder_id:
                    # Show lists in folder
                    lists = await client.get_lists(folder_id)
                    if lists:
                        table = Table(title=f"Lists in Folder {folder_id}")
                        table.add_column("Name", style="green")
                        table.add_column("ID", style="cyan")
                        table.add_column("Tasks", style="yellow")

                        for lst in lists:
                            table.add_row(lst.name, lst.id, str(lst.task_count))
                        console.print(table)
                    else:
                        console.print("[yellow]No lists found in this folder.[/yellow]")

                elif space_id:
                    # Show folders and folderless lists in space
                    table = Table(title=f"Folders and Lists in Space {space_id}")
                    table.add_column("Type", style="blue")
                    table.add_column("Name", style="green")
                    table.add_column("ID", style="cyan")
                    table.add_column("Info", style="yellow")

                    try:
                        folders = await client.get_folders(space_id)
                        for folder in folders:
                            table.add_row("📂 Folder", folder.name, folder.id, f"{folder.task_count} tasks")
                    except ClickUpError:
                        pass

                    try:
                        lists = await client.get_folderless_lists(space_id)
                        for lst in lists:
                            table.add_row("📋 List", lst.name, lst.id, f"{lst.task_count} tasks")
                    except ClickUpError:
                        pass

                    console.print(table)

                elif workspace_id or team_id:
                    # Show spaces in workspace
                    id_to_use = workspace_id or team_id
                    assert id_to_use is not None  # guaranteed by elif condition
                    spaces = await client.get_spaces(id_to_use)
                    if spaces:
                        table = Table(title=f"Spaces in Workspace {id_to_use}")
                        table.add_column("Name", style="blue")
                        table.add_column("ID", style="cyan")
                        table.add_column("Private", style="yellow")
                        table.add_column("Statuses", style="green")

                        for space in spaces:
                            table.add_row(
                                space.name, space.id, "Yes" if space.private else "No", str(len(space.statuses))
                            )
                        console.print(table)
                    else:
                        console.print("[yellow]No spaces found in this workspace.[/yellow]")

                else:
                    # Show workspaces
                    workspaces = await client.get_teams()
                    if workspaces:
                        table = Table(title="Workspaces")
                        table.add_column("Name", style="cyan")
                        table.add_column("ID", style="blue")
                        table.add_column("Color", style="green")
                        table.add_column("Members", style="yellow")

                        for workspace in workspaces:
                            table.add_row(
                                workspace.name, workspace.id, workspace.color or "N/A", str(len(workspace.members))
                            )
                        console.print(table)

                        console.print(
                            "\n💡 [dim]Use --workspace-id to see spaces, --space-id to see folders/lists, "
                            "--folder-id to see lists[/dim]"
                        )

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_show_ids())


@app.command("path")
def find_path(list_id: str = typer.Argument(..., help="List ID to find path for")) -> None:
    """Show the full path to a list (Workspace > Space > Folder > List)."""

    async def _find_path() -> None:
        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Finding path...", total=None)

                    # Get list details
                    lst = await client.get_list(list_id)

                    # Build path by working backwards
                    path_parts = []
                    path_parts.append(f"📋 [green]{lst.name}[/green] ([dim]{lst.id}[/dim])")

                    # Find which folder/space contains this list
                    workspaces = await client.get_teams()
                    found_path = False

                    for workspace in workspaces:
                        if found_path:
                            break

                        try:
                            spaces = await client.get_spaces(workspace.id)
                            for space in spaces:
                                if found_path:
                                    break

                                # Check folderless lists first
                                try:
                                    folderless_lists = await client.get_folderless_lists(space.id)
                                    if any(lst.id == list_id for lst in folderless_lists):
                                        path_parts.insert(0, f"📁 [blue]{space.name}[/blue] ([dim]{space.id}[/dim])")
                                        path_parts.insert(
                                            0, f"🏢 [cyan]{workspace.name}[/cyan] ([dim]{workspace.id}[/dim])"
                                        )
                                        found_path = True
                                        break
                                except ClickUpError:
                                    pass

                                # Check folders
                                try:
                                    folders = await client.get_folders(space.id)
                                    for folder in folders:
                                        try:
                                            lists = await client.get_lists(folder.id)
                                            if any(lst.id == list_id for lst in lists):
                                                path_parts.insert(
                                                    0, f"📂 [yellow]{folder.name}[/yellow] ([dim]{folder.id}[/dim])"
                                                )
                                                path_parts.insert(
                                                    0, f"📁 [blue]{space.name}[/blue] ([dim]{space.id}[/dim])"
                                                )
                                                path_parts.insert(
                                                    0, f"🏢 [cyan]{workspace.name}[/cyan] ([dim]{workspace.id}[/dim])"
                                                )
                                                found_path = True
                                                break
                                        except ClickUpError:
                                            pass
                                except ClickUpError:
                                    pass
                        except ClickUpError:
                            pass

                    if found_path:
                        console.print("\n📍 [bold]Path to List:[/bold]")
                        for i, part in enumerate(path_parts):
                            indent = "  " * i
                            console.print(f"{indent}{part}")
                    else:
                        console.print(f"[yellow]Could not find path for list {list_id}[/yellow]")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e

    run_async(_find_path())
