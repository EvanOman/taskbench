"""Bulk operations and import/export commands."""

import csv
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from ...core import ClickUpClient, ClickUpError, Config
from ..utils import run_async

app = typer.Typer(help="Bulk operations and import/export")
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


@app.command("export-tasks")
def export_tasks(
    list_id: str | None = typer.Option(None, "--list-id", help="List ID to export tasks from"),
    output_file: str = typer.Option("tasks.csv", "--output", "-o", help="Output file path"),
    format: str = typer.Option("csv", "--format", "-f", help="Output format (csv, json)"),
    include_completed: bool = typer.Option(True, "--include-completed", help="Include completed tasks"),
) -> None:
    """Export tasks to CSV or JSON file."""

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
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task_id = progress.add_task("Fetching tasks...", total=None)

                    filters = {}
                    if not include_completed:
                        filters["include_closed"] = False

                    tasks = await client.get_tasks(list_id_to_use, **filters)
                    progress.update(task_id, description=f"Exporting {len(tasks)} tasks...")

                    if format.lower() == "csv":
                        # Export to CSV
                        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
                            fieldnames = [
                                "id",
                                "name",
                                "description",
                                "status",
                                "priority",
                                "assignees",
                                "due_date",
                                "date_created",
                                "date_updated",
                                "url",
                            ]
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
                                        "description": task.description or "",
                                        "status": status,
                                        "priority": priority,
                                        "assignees": assignees,
                                        "due_date": task.due_date or "",
                                        "date_created": task.date_created or "",
                                        "date_updated": task.date_updated or "",
                                        "url": task.url or "",
                                    }
                                )

                    elif format.lower() == "json":
                        # Export to JSON
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

                    else:
                        console.print(f"[red]Unsupported format: {format}[/red]")
                        raise typer.Exit(1) from None

                    progress.update(task_id, description="✅ Export completed", completed=True)

                console.print(f"✅ Exported {len(tasks)} tasks to {output_file}")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_export_tasks())


@app.command("import-tasks")
def import_tasks(
    input_file: str = typer.Argument(..., help="Input file path (CSV or JSON)"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to import tasks into"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview import without creating tasks"),
    batch_size: int = typer.Option(10, "--batch-size", help="Number of tasks to create in parallel"),
) -> None:
    """Import tasks from CSV or JSON file."""

    async def _import_tasks() -> None:
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            console.print("[red]Error: No list ID provided and no default list configured.[/red]")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        try:
            file_path = Path(input_file)
            if not file_path.exists():
                console.print(f"[red]File not found: {input_file}[/red]")
                raise typer.Exit(1)

            # Read and parse file
            tasks_data = []
            if file_path.suffix.lower() == ".csv":
                with open(file_path, encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)
                    tasks_data = list(reader)
            elif file_path.suffix.lower() == ".json":
                with open(file_path, encoding="utf-8") as jsonfile:
                    tasks_data = json.load(jsonfile)
            else:
                console.print(f"[red]Unsupported file format: {file_path.suffix}[/red]")
                raise typer.Exit(1)

            if not tasks_data:
                console.print("[yellow]No tasks found in file.[/yellow]")
                return

            console.print(f"Found {len(tasks_data)} tasks to import")

            if dry_run:
                # Preview mode
                table = Table(title="Import Preview", show_header=True)
                table.add_column("Name", style="bold")
                table.add_column("Description", style="dim")
                table.add_column("Priority", style="yellow")
                table.add_column("Assignees", style="blue")

                for task_data in tasks_data[:10]:  # Show first 10
                    table.add_row(
                        task_data.get("name", ""),
                        task_data.get("description", "")[:50] + "..."
                        if len(task_data.get("description", "")) > 50
                        else task_data.get("description", ""),
                        str(task_data.get("priority", "")),
                        task_data.get("assignees", ""),
                    )

                console.print(table)
                if len(tasks_data) > 10:
                    console.print(f"... and {len(tasks_data) - 10} more tasks")
                console.print("[yellow]This was a dry run. Use --no-dry-run to actually import.[/yellow]")
                return

            # Confirm import
            if not typer.confirm(f"Import {len(tasks_data)} tasks into list {list_id_to_use}?"):
                console.print("Import cancelled.")
                return

            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    import_task = progress.add_task("Importing tasks...", total=len(tasks_data))

                    created_count = 0
                    failed_count = 0

                    # Process in batches
                    for i in range(0, len(tasks_data), batch_size):
                        batch = tasks_data[i : i + batch_size]

                        for task_data in batch:
                            try:
                                # Prepare task creation data
                                create_data: dict[str, Any] = {"name": task_data.get("name", "Untitled Task")}

                                if task_data.get("description"):
                                    create_data["description"] = task_data["description"]
                                if task_data.get("priority"):
                                    try:
                                        create_data["priority"] = int(task_data["priority"])
                                    except (ValueError, TypeError):
                                        pass
                                if task_data.get("due_date"):
                                    create_data["due_date"] = task_data["due_date"]

                                # Create task
                                await client.create_task(list_id_to_use, **create_data)
                                created_count += 1

                            except Exception as e:
                                console.print(
                                    f"[yellow]Failed to create task '{task_data.get('name', 'Unknown')}': {e}[/yellow]"
                                )
                                failed_count += 1

                            progress.advance(import_task)

                    progress.update(import_task, description="✅ Import completed")

                console.print(f"✅ Import completed: {created_count} created, {failed_count} failed")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_import_tasks())


@app.command("bulk-update")
def bulk_update(
    list_id: str | None = typer.Option(None, "--list-id", help="List ID to update tasks in"),
    filter_status: str | None = typer.Option(None, "--filter-status", help="Only update tasks with this status"),
    new_status: str | None = typer.Option(None, "--status", help="New status to set"),
    new_priority: int | None = typer.Option(None, "--priority", help="New priority to set (1-4)"),
    new_assignee: str | None = typer.Option(None, "--assignee", help="New assignee user ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
) -> None:
    """Bulk update tasks matching criteria."""

    async def _bulk_update() -> None:
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            console.print("[red]Error: No list ID provided and no default list configured.[/red]")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        if not any([new_status, new_priority, new_assignee]):
            console.print("[red]Error: Must specify at least one update (--status, --priority, or --assignee)[/red]")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    fetch_task = progress.add_task("Fetching tasks...", total=None)

                    filters = {}
                    if filter_status:
                        filters["statuses"] = [filter_status]

                    tasks = await client.get_tasks(list_id_to_use, **filters)
                    progress.update(fetch_task, description=f"Found {len(tasks)} tasks")

                    if not tasks:
                        console.print("[yellow]No tasks found matching criteria.[/yellow]")
                        return

                    # Preview changes
                    table = Table(title="Bulk Update Preview", show_header=True)
                    table.add_column("Task", style="bold")
                    table.add_column("Current Status", style="blue")
                    table.add_column("New Status", style="green")
                    table.add_column("Current Priority", style="yellow")
                    table.add_column("New Priority", style="yellow")

                    updates: dict[str, Any] = {}
                    if new_status:
                        updates["status"] = new_status
                    if new_priority:
                        updates["priority"] = new_priority
                    if new_assignee:
                        updates["assignees"] = [new_assignee]

                    for task in tasks[:10]:  # Show first 10
                        current_status = task.status.get("status", "Unknown") if task.status else "Unknown"
                        current_priority = task.priority.get("priority", "None") if task.priority else "None"

                        table.add_row(
                            task.name[:30] + "..." if len(task.name) > 30 else task.name,
                            current_status,
                            new_status or current_status,
                            current_priority,
                            str(new_priority) if new_priority else current_priority,
                        )

                    console.print(table)
                    if len(tasks) > 10:
                        console.print(f"... and {len(tasks) - 10} more tasks")

                    if dry_run:
                        console.print("[yellow]This was a dry run. Remove --dry-run to apply changes.[/yellow]")
                        return

                    if not typer.confirm(f"Apply updates to {len(tasks)} tasks?"):
                        console.print("Bulk update cancelled.")
                        return

                    # Apply updates
                    update_task = progress.add_task("Updating tasks...", total=len(tasks))
                    updated_count = 0
                    failed_count = 0

                    for task in tasks:
                        try:
                            await client.update_task(task.id, **updates)
                            updated_count += 1
                        except Exception as e:
                            console.print(f"[yellow]Failed to update task '{task.name}': {e}[/yellow]")
                            failed_count += 1

                        progress.advance(update_task)

                    progress.update(update_task, description="✅ Bulk update completed")

                console.print(f"✅ Bulk update completed: {updated_count} updated, {failed_count} failed")

        except ClickUpError as e:
            console.print(f"[red]ClickUp API Error: {e}[/red]")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_bulk_update())
