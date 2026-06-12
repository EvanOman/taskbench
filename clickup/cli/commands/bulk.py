"""Bulk operations and import/export commands."""

import csv
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...core import ClickUpError
from ..output import _print_json, get_format, render_error, render_kv, render_message
from ..shared import gather_bounded, get_client, require_list_id, resolve_list_ids
from ..utils import run_async

app = typer.Typer(help="Bulk operations and import/export")
console = Console()


@app.command("export-tasks")
def export_tasks(
    list_id: str | None = typer.Option(None, "--list-id", help="List ID to export tasks from"),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output file path (default: tasks.<format>)"),
    output_format: str = typer.Option("json", "--output-format", "--format", "-f", help="Output format (json, csv)"),
    include_completed: bool = typer.Option(True, "--include-completed", help="Include completed tasks"),
) -> None:
    """Export tasks to JSON or CSV file."""

    async def _export_tasks() -> None:
        list_id_to_use = require_list_id(list_id)
        nonlocal output_file
        output_file = output_file or f"tasks.{output_format.lower()}"

        try:
            async with await get_client() as client:
                filters = {}
                if not include_completed:
                    filters["include_closed"] = False

                tasks = await client.get_tasks(list_id_to_use, **filters)

                if output_format.lower() == "csv":
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

                elif output_format.lower() == "json":
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
                    render_error(f"Unsupported format: {output_format}")
                    raise typer.Exit(1) from None
                render_kv({"exported": len(tasks), "output_file": output_file, "format": output_format.lower()})

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_export_tasks())


@app.command("import-tasks")
def import_tasks(
    input_file: str = typer.Argument(..., help="Input file path (CSV or JSON)"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to import tasks into"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview import without creating tasks"),
    batch_size: int = typer.Option(10, "--batch-size", help="Number of tasks to create in parallel"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to actually import. No interactive prompt.",
    ),
) -> None:
    """Import tasks from CSV or JSON file."""

    async def _import_tasks() -> None:
        list_id_to_use = require_list_id(list_id)

        try:
            file_path = Path(input_file)
            if not file_path.exists():
                render_error(f"File not found: {input_file}")
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
                render_error(f"Unsupported file format: {file_path.suffix}")
                raise typer.Exit(1)

            if not tasks_data:
                render_message("No tasks found in file.", level="info")
                return

            render_message(f"Found {len(tasks_data)} tasks to import", level="info")

            if dry_run:
                if get_format() == "json":
                    _print_json(
                        {
                            "dry_run": True,
                            "would_create": len(tasks_data),
                            "tasks": tasks_data[:10],
                        }
                    )
                    return

                table = Table(title="Import Preview", show_header=True)
                table.add_column("Name", style="bold")
                table.add_column("Description", style="dim")
                table.add_column("Priority", style="yellow")
                table.add_column("Assignees", style="blue")

                for task_data in tasks_data[:10]:
                    table.add_row(
                        escape(task_data.get("name", "")),
                        escape(
                            task_data.get("description", "")[:50] + "..."
                            if len(task_data.get("description", "")) > 50
                            else task_data.get("description", "")
                        ),
                        str(task_data.get("priority", "")),
                        escape(task_data.get("assignees", "")),
                    )

                console.print(table)
                if len(tasks_data) > 10:
                    render_message(f"... and {len(tasks_data) - 10} more tasks", level="info")
                render_message("This was a dry run. Use --no-dry-run to actually import.", level="info")
                return

            if not force:
                render_error(
                    f"Refusing to import {len(tasks_data)} tasks without --force/--yes (use --dry-run to preview).",
                    error_type="UsageError",
                )
                raise typer.Exit(2)

            async with await get_client() as client:
                created_count = 0
                failed_count = 0

                def _prepare(td: dict[str, Any]) -> dict[str, Any]:
                    d: dict[str, Any] = {"name": td.get("name", "Untitled Task")}
                    if td.get("description"):
                        d["description"] = td["description"]
                    if td.get("priority"):
                        try:
                            d["priority"] = int(td["priority"])
                        except (ValueError, TypeError):
                            pass
                    if td.get("due_date"):
                        d["due_date"] = td["due_date"]
                    return d

                # Process in batches with bounded concurrency
                for i in range(0, len(tasks_data), batch_size):
                    batch = tasks_data[i : i + batch_size]
                    coros = [client.create_task(list_id_to_use, **_prepare(td)) for td in batch]
                    results = await gather_bounded(coros, limit=batch_size)
                    for td, result in zip(batch, results, strict=False):
                        if isinstance(result, BaseException):
                            render_message(
                                f"Failed to create task '{td.get('name', 'Unknown')}': {result}",
                                level="warn",
                            )
                            failed_count += 1
                        else:
                            created_count += 1

                summary: dict[str, Any] = {"created": created_count, "failed": failed_count}
                render_kv(summary)
                if failed_count:
                    raise typer.Exit(1)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_import_tasks())


@app.command("bulk-update")
def bulk_update(
    list_id: str | None = typer.Option(None, "--list-id", help="List ID to update tasks in"),
    all_lists: bool = typer.Option(
        False,
        "--all-lists",
        help=(
            "Update tasks across every list configured in the default_lists aliases — NOT every "
            "list in the workspace. See configured aliases with 'clickup config get default_lists'."
        ),
    ),
    filter_status: str | None = typer.Option(None, "--filter-status", help="Only update tasks with this status"),
    new_status: str | None = typer.Option(None, "--status", help="New status to set"),
    new_priority: int | None = typer.Option(
        None,
        "--priority",
        help="New priority to set (1=urgent, 2=high, 3=normal, 4=low).",
    ),
    new_assignee: str | None = typer.Option(None, "--assignee", help="New assignee user ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to actually apply updates. No interactive prompt.",
    ),
) -> None:
    """Bulk update tasks matching criteria."""

    async def _bulk_update() -> None:
        list_ids_to_use = resolve_list_ids(list_id, all_lists=all_lists)

        if not list_ids_to_use:
            render_error(
                "Error: No list ID provided and no default list configured.",
                hint="Use --list-id or set a default with 'clickup config set default_list_id <id>'",
            )
            raise typer.Exit(2)

        if new_status is None and new_priority is None and new_assignee is None:
            render_error("Error: Must specify at least one update (--status, --priority, or --assignee)")
            raise typer.Exit(1)

        try:
            async with await get_client() as client:
                filters: dict[str, Any] = {}
                if filter_status:
                    filters["statuses"] = [filter_status]

                # Gather tasks across all lists (bounded concurrency)
                all_tasks: list[tuple[str, Any]] = []  # (list_id, task) pairs
                fetch_results = await gather_bounded(
                    [client.get_tasks(lid, **filters) for lid in list_ids_to_use],
                    limit=5,
                )
                for lid, result in zip(list_ids_to_use, fetch_results, strict=False):
                    if isinstance(result, BaseException):
                        render_message(f"Failed to fetch tasks from list {lid}: {result}", level="warn")
                    else:
                        all_tasks.extend((lid, t) for t in result)

                if not all_tasks:
                    render_message("No tasks found matching criteria.", level="info")
                    return

                updates: dict[str, Any] = {}
                if new_status is not None:
                    updates["status"] = new_status
                if new_priority is not None:
                    updates["priority"] = new_priority
                if new_assignee is not None:
                    updates["assignees"] = [new_assignee]

                if dry_run:
                    if get_format() == "json":
                        _print_json(
                            {
                                "dry_run": True,
                                "would_update": len(all_tasks),
                                "updates": updates,
                                "tasks": [{"id": task.id, "name": task.name} for _lid, task in all_tasks],
                            }
                        )
                        return

                table = Table(title="Bulk Update Preview", show_header=True)
                table.add_column("Task", style="bold")
                if len(list_ids_to_use) > 1:
                    table.add_column("List", style="dim")
                table.add_column("Current Status", style="blue")
                table.add_column("New Status", style="green")
                table.add_column("Current Priority", style="yellow")
                table.add_column("New Priority", style="yellow")

                for lid, task in all_tasks[:10]:
                    current_status = task.status.status if task.status else "Unknown"
                    current_priority = (task.priority.priority or "None") if task.priority else "None"
                    row = [escape(task.name[:30] + "..." if len(task.name) > 30 else task.name)]
                    if len(list_ids_to_use) > 1:
                        row.append(lid)
                    row.extend(
                        [
                            escape(current_status),
                            escape(new_status or current_status),
                            current_priority,
                            str(new_priority) if new_priority else current_priority,
                        ]
                    )
                    table.add_row(*row)

                console.print(table)
                if len(all_tasks) > 10:
                    render_message(f"... and {len(all_tasks) - 10} more tasks", level="info")

                if dry_run:
                    render_message("This was a dry run. Remove --dry-run to apply changes.", level="info")
                    return

                if not force:
                    render_error(
                        f"Refusing to update {len(all_tasks)} tasks without --force/--yes (use --dry-run to preview).",
                        error_type="UsageError",
                    )
                    raise typer.Exit(2)

                # Apply updates — bounded concurrency, continue through failures
                update_results = await gather_bounded(
                    [client.update_task(task.id, **updates) for _lid, task in all_tasks],
                    limit=5,
                )
                updated_count = 0
                failed_count = 0
                for (_lid, task), result in zip(all_tasks, update_results, strict=False):
                    if isinstance(result, BaseException):
                        render_message(f"Failed to update task '{task.name}': {result}", level="warn")
                        failed_count += 1
                    else:
                        updated_count += 1

                summary: dict[str, Any] = {"updated": updated_count, "failed": failed_count}
                render_kv(summary)
                if failed_count:
                    raise typer.Exit(1)

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e
        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_bulk_update())
