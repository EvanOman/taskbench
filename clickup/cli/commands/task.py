"""Task management commands."""

from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...core import ClickUpClient, ClickUpError, Config, Task
from ..utils import run_async

app = typer.Typer(help="Task management")
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


def format_task_table(tasks: list[Task]) -> Table:
    """Format tasks as a rich table."""
    table = Table(title="Tasks", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status", style="green")
    table.add_column("Assignees", style="blue")
    table.add_column("Priority", style="yellow")
    table.add_column("Due Date", style="red")

    for task in tasks:
        status = task.status.status if task.status else "Unknown"
        assignees = ", ".join([a.username for a in task.assignees]) if task.assignees else "Unassigned"
        priority = task.priority.priority or "None" if task.priority else "None"
        due_date = task.due_date or "None"

        table.add_row(task.id, task.name, status, assignees, priority, due_date)

    return table


@app.command("list")
def list_tasks(
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to get tasks from"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Filter by assignee"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of tasks to show"),
) -> None:
    """List tasks from a ClickUp list."""

    async def _list_tasks() -> None:
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            console.print("[red]Error: No list ID provided and no default list configured.[/red]")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Fetching tasks...", total=None)

                    filters = {}
                    if status:
                        filters["statuses"] = [status]
                    if assignee:
                        filters["assignees"] = [assignee]

                    tasks = await client.get_tasks(list_id_to_use, **filters)

                if not tasks:
                    console.print("[yellow]No tasks found.[/yellow]")
                    return

                # Apply limit
                tasks = tasks[:limit]
                table = format_task_table(tasks)
                console.print(table)

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_list_tasks())


@app.command("get")
def get_task(task_id: str = typer.Argument(..., help="Task ID")) -> None:
    """Get detailed information about a specific task."""

    async def _get_task() -> None:
        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Fetching task...", total=None)
                    task = await client.get_task(task_id)

                # Create detailed task info table
                table = Table(title=f"Task: {task.name}", show_header=False)
                table.add_column("Field", style="cyan", width=15)
                table.add_column("Value", style="white")

                table.add_row("ID", task.id)
                table.add_row("Name", task.name)
                table.add_row("Description", task.description or "None")
                table.add_row("Status", task.status.status if task.status else "Unknown")
                table.add_row(
                    "Assignees", ", ".join([a.username for a in task.assignees]) if task.assignees else "Unassigned"
                )
                table.add_row("Priority", task.priority.priority or "None" if task.priority else "None")
                table.add_row("Due Date", task.due_date or "None")
                table.add_row("Created", task.date_created or "Unknown")
                table.add_row("Updated", task.date_updated or "Unknown")
                table.add_row("URL", task.url or "None")

                console.print(table)

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_get_task())


@app.command("create")
def create_task(
    name: str = typer.Argument(..., help="Task name"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to create task in"),
    description: str | None = typer.Option(None, "--description", "-d", help="Task description"),
    priority: int | None = typer.Option(None, "--priority", "-p", help="Priority (1=urgent, 4=low)"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Assignee user ID"),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
) -> None:
    """Create a new task."""

    async def _create_task() -> None:
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            console.print("[red]Error: No list ID provided and no default list configured.[/red]")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            task_data: dict[str, Any] = {"name": name}

            if description:
                task_data["description"] = description
            if priority:
                task_data["priority"] = priority
            if assignee:
                task_data["assignees"] = [assignee]
            if due_date:
                # Convert to timestamp (simplified)
                task_data["due_date"] = due_date

            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Creating task...", total=None)
                    task = await client.create_task(list_id_to_use, **task_data)

                console.print(f"✅ Created task: {task.name} (ID: {task.id})")
                if task.url:
                    console.print(f"🔗 URL: {task.url}")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_create_task())


@app.command("update")
def update_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="New task name"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description (pass '' to clear)"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    priority: int | None = typer.Option(None, "--priority", "-p", help="New priority (1-4)"),
    due_date: str | None = typer.Option(None, "--due-date", help="New due date (ms timestamp)"),
    archived: bool | None = typer.Option(None, "--archived/--unarchived", help="Archive state"),
) -> None:
    """Update a task. Only fields you pass are changed; everything else stays the same."""

    async def _update_task() -> None:
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
            console.print("[yellow]No updates specified.[/yellow]")
            return

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Updating task...", total=None)
                    task = await client.update_task(task_id, **updates)

                console.print(f"✅ Updated task: {task.name} (ID: {task.id})")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_update_task())


@app.command("status")
def change_status(
    task_id: str | None = typer.Option(None, "--task-id", "-t", help="Task ID"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
) -> None:
    """Change task status."""

    async def _change_status() -> None:
        if not task_id:
            console.print("[red]Error: Task ID is required.[/red]")
            console.print("Use --task-id to specify the task")
            raise typer.Exit(1)

        if not status:
            console.print("[red]Error: Status is required.[/red]")
            console.print("Use --status to specify the new status")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Updating task status...", total=None)
                    task = await client.update_task(task_id, status=status)

                console.print(f"✅ Updated task status: {task.name} → {status}")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_change_status())


@app.command("delete")
def delete_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a task."""

    async def _delete_task() -> None:
        if not force:
            if not typer.confirm(f"Are you sure you want to delete task {task_id}?"):
                console.print("Cancelled.")
                return

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Deleting task...", total=None)
                    await client.delete_task(task_id)

                console.print(f"✅ Deleted task {task_id}")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_delete_task())


@app.command("search")
def search_tasks(
    query: str | None = typer.Option(None, "--query", "-q", help="Search query"),
    workspace_id: str | None = typer.Option(None, "--workspace-id", "-w", help="Workspace ID to search in"),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
) -> None:
    """Search for tasks across the workspace."""

    async def _search_tasks() -> None:
        if not query:
            console.print("[red]Error: Search query is required.[/red]")
            console.print("Use --query to specify the search terms")
            raise typer.Exit(1)

        # Use either workspace_id or team_id (they're the same thing)
        id_to_use = workspace_id or team_id
        if not id_to_use:
            console.print("[red]Error: Workspace ID is required for search.[/red]")
            console.print("Use --workspace-id or --team-id to specify the workspace")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Searching tasks...", total=None)
                    tasks = await client.search_tasks(id_to_use, query)

                if not tasks:
                    console.print(f"[yellow]No tasks found matching '{query}'[/yellow]")
                    return

                table = Table(title=f"Search Results for '{query}'", show_header=True)
                table.add_column("ID", style="cyan")
                table.add_column("Name", style="bold")
                table.add_column("Status", style="green")
                table.add_column("Assignees", style="blue")
                table.add_column("Priority", style="yellow")
                table.add_column("Due Date", style="red")

                for task in tasks:
                    status = task.status.status if task.status else "Unknown"
                    assignees = ", ".join([a.username for a in task.assignees]) if task.assignees else "Unassigned"
                    priority = task.priority.priority or "None" if task.priority else "None"
                    due_date = task.due_date or "None"

                    table.add_row(task.id, task.name, status, assignees, priority, due_date)

                console.print(table)
                console.print(f"\n[dim]Found {len(tasks)} tasks[/dim]")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
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
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            console.print("[red]Error: No list ID provided and no default list configured.[/red]")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Exporting tasks...", total=None)

                    filters = {}
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
                            status = task.status.status if task.status else ""
                            priority = task.priority.priority or "" if task.priority else ""
                            assignees = ", ".join([a.username for a in task.assignees]) if task.assignees else ""

                            writer.writerow(
                                {
                                    "id": task.id,
                                    "name": task.name,
                                    "status": status,
                                    "priority": priority,
                                    "assignees": assignees,
                                    "due_date": task.due_date or "",
                                    "description": task.description or "",
                                }
                            )
                else:
                    console.print(f"[red]Unsupported format: {format}[/red]")
                    raise typer.Exit(1)

                console.print(f"✅ Exported {len(tasks)} tasks to {output_file}")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_export_tasks())
