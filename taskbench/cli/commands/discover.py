"""Discovery commands for navigating ClickUp hierarchy."""

import typer
from rich.markup import escape

from ...core import ClickUpError
from ..output import (
    get_format,
    render_hierarchy,
    render_id_rows,
    render_lists,
    render_message,
    render_path,
    render_spaces,
    render_teams,
)
from ..shared import get_client, handle_clickup_errors
from ..utils import run_async

app = typer.Typer(help="Discover and navigate ClickUp hierarchy")


@app.command("hierarchy")
def show_hierarchy(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", "-w", help="Workspace ID (will list all if not provided)"
    ),
    team_id: str | None = typer.Option(None, "--team-id", "-t", help="Team ID (alias for workspace-id)"),
    max_depth: int = typer.Option(
        5,
        "--depth",
        "-d",
        help=(
            "Maximum depth to explore (1=workspaces, 2=+spaces, 3=+folders, 4=+lists, 5=full). "
            "Defaults to the full tree; lower it to trim API calls on large workspaces."
        ),
    ),
) -> None:
    """Show the complete ClickUp hierarchy tree."""

    async def _show_hierarchy() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                id_to_use = workspace_id or team_id
                workspaces = [await client.get_team(id_to_use)] if id_to_use else await client.get_teams()

                truncated = False
                data: dict = {"workspaces": []}
                for workspace in workspaces:
                    ws_dict: dict = {"id": workspace.id, "name": workspace.name, "spaces": []}
                    if max_depth >= 2:
                        try:
                            spaces = await client.get_spaces(workspace.id)
                        except ClickUpError:
                            spaces = []
                        for space in spaces:
                            sp_dict: dict = {
                                "id": space.id,
                                "name": space.name,
                                "folders": [],
                                "folderless_lists": [],
                            }
                            if max_depth >= 3:
                                try:
                                    folders = await client.get_folders(space.id)
                                except ClickUpError:
                                    folders = []
                                for folder in folders:
                                    f_dict: dict = {"id": folder.id, "name": folder.name, "lists": []}
                                    if max_depth >= 4:
                                        try:
                                            lists = await client.get_lists(folder.id)
                                            f_dict["lists"] = [
                                                {"id": lst.id, "name": lst.name, "task_count": lst.task_count}
                                                for lst in lists
                                            ]
                                        except ClickUpError:
                                            pass
                                    else:
                                        f_dict["truncated_at_depth"] = True
                                        truncated = True
                                    sp_dict["folders"].append(f_dict)
                                try:
                                    folderless = await client.get_folderless_lists(space.id)
                                    sp_dict["folderless_lists"] = [
                                        {"id": lst.id, "name": lst.name, "task_count": lst.task_count}
                                        for lst in folderless
                                    ]
                                except ClickUpError:
                                    pass
                            else:
                                sp_dict["truncated_at_depth"] = True
                                truncated = True
                            ws_dict["spaces"].append(sp_dict)
                    else:
                        ws_dict["truncated_at_depth"] = True
                        truncated = True
                    data["workspaces"].append(ws_dict)

                render_hierarchy(data)
                if truncated and get_format() != "json":
                    render_message(
                        f"Output truncated at --depth {max_depth}. Increase --depth to see deeper levels.",
                        level="warn",
                    )

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
        with handle_clickup_errors():
            async with await get_client() as client:
                if folder_id:
                    lists = await client.get_lists(folder_id)
                    if lists:
                        render_lists(lists)
                    else:
                        render_message("No lists found in this folder.", level="info")

                elif space_id:
                    rows: list[dict[str, str]] = []
                    try:
                        folders = await client.get_folders(space_id)
                        for folder in folders:
                            rows.append(
                                {
                                    "type": "folder",
                                    "name": folder.name,
                                    "id": folder.id,
                                    "info": f"{folder.task_count} tasks",
                                }
                            )
                    except ClickUpError:
                        pass

                    try:
                        lists = await client.get_folderless_lists(space_id)
                        for lst in lists:
                            rows.append(
                                {
                                    "type": "list",
                                    "name": lst.name,
                                    "id": lst.id,
                                    "info": f"{lst.task_count} tasks",
                                }
                            )
                    except ClickUpError:
                        pass

                    render_id_rows(rows, title=f"Folders and Lists in Space {escape(space_id)}")

                elif workspace_id or team_id:
                    id_to_use = workspace_id or team_id
                    assert id_to_use is not None
                    spaces = await client.get_spaces(id_to_use)
                    if spaces:
                        render_spaces(spaces)
                    else:
                        render_message("No spaces found in this workspace.", level="info")

                else:
                    workspaces = await client.get_teams()
                    if workspaces:
                        render_teams(workspaces)
                        render_message(
                            "Use --workspace-id to see spaces, --space-id to see folders/lists, "
                            "--folder-id to see lists",
                            level="info",
                        )

    run_async(_show_ids())


@app.command("path")
def find_path(list_id: str = typer.Argument(..., help="List ID to find path for")) -> None:
    """Show the full path to a list (Workspace > Space > Folder > List)."""

    async def _find_path() -> None:
        with handle_clickup_errors():
            async with await get_client() as client:
                lst = await client.get_list(list_id)
                lst_dict = {"id": lst.id, "name": lst.name}

                workspaces = await client.get_teams()
                found = False
                path: list[dict[str, str]] = []

                for workspace in workspaces:
                    if found:
                        break
                    try:
                        spaces = await client.get_spaces(workspace.id)
                        for space in spaces:
                            if found:
                                break
                            try:
                                folderless_lists = await client.get_folderless_lists(space.id)
                                if any(fl.id == list_id for fl in folderless_lists):
                                    path = [
                                        {"type": "workspace", "id": workspace.id, "name": workspace.name},
                                        {"type": "space", "id": space.id, "name": space.name},
                                        {"type": "list", "id": lst.id, "name": lst.name},
                                    ]
                                    found = True
                                    break
                            except ClickUpError:
                                pass
                            try:
                                folders = await client.get_folders(space.id)
                                for folder in folders:
                                    try:
                                        lists = await client.get_lists(folder.id)
                                        if any(fl.id == list_id for fl in lists):
                                            path = [
                                                {"type": "workspace", "id": workspace.id, "name": workspace.name},
                                                {"type": "space", "id": space.id, "name": space.name},
                                                {"type": "folder", "id": folder.id, "name": folder.name},
                                                {"type": "list", "id": lst.id, "name": lst.name},
                                            ]
                                            found = True
                                            break
                                    except ClickUpError:
                                        pass
                            except ClickUpError:
                                pass
                    except ClickUpError:
                        pass

                render_path(lst_dict, path, found)

    run_async(_find_path())
