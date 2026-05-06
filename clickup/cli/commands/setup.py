"""Setup wizard for ClickUp CLI.

Supports both interactive (human-driven) and non-interactive (agent-driven)
flows. Pass ``--token``, ``--team-id``, ``--space-id`` and ``--list-id`` to
configure defaults without prompts. ``--non-interactive`` makes any
required-but-missing value an error rather than a prompt.
"""

import typer
from rich.console import Console
from rich.table import Table

from ...core import ClickUpClient, Config
from ...core.models import List as ClickUpList
from ..output import render_error, render_message
from ..utils import run_async

app = typer.Typer(help="Setup and onboarding")
console = Console()


class _NeedsInput(Exception):
    """Raised when --non-interactive is set but a value would otherwise be prompted."""


def _pick_from_menu(
    items: list[tuple[str, str]], prompt_text: str, *, non_interactive: bool, missing_flag: str
) -> tuple[str, str]:
    """Present a numbered menu and return (id, name) of the chosen item."""
    if non_interactive:
        raise _NeedsInput(f"Multiple options available — pass {missing_flag} to choose without a prompt.")

    console.print(f"\n[bold]{prompt_text}[/bold]")
    for idx, (item_id, name) in enumerate(items, 1):
        console.print(f"  [cyan]{idx}[/cyan]) {name} (ID: {item_id})")

    while True:
        raw = typer.prompt("Enter number", default="1")
        try:
            choice = int(raw)
            if 1 <= choice <= len(items):
                return items[choice - 1]
        except ValueError:
            pass
        render_error(f"Please enter a number between 1 and {len(items)}.")


def _suggest_most_active(lists: list[ClickUpList]) -> ClickUpList | None:
    """Return the list with the highest task count (most-active heuristic)."""
    if not lists:
        return None
    return max(lists, key=lambda lst: (lst.task_count or 0, lst.name))


@app.command("run")
def setup_wizard(
    token: str | None = typer.Option(None, "--token", help="ClickUp API token (skips token prompt)."),
    team_id: str | None = typer.Option(
        None, "--team-id", "--workspace-id", help="Default team/workspace ID (skips workspace prompt)."
    ),
    space_id: str | None = typer.Option(None, "--space-id", help="Default space ID (skips space prompt)."),
    list_id: str | None = typer.Option(None, "--list-id", help="Default list ID (skips list prompt)."),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Fail instead of prompting when a value is missing. Use with --token/--team-id/etc.",
    ),
) -> None:
    """Setup wizard — configure defaults for the ClickUp CLI.

    Interactive by default. To run non-interactively (agent flow), pass
    --token / --team-id / --space-id / --list-id and (optionally)
    --non-interactive to error on any missing value rather than prompt.
    """

    async def _setup() -> None:
        config = Config()

        console.print("\n[bold]ClickUp CLI Setup Wizard[/bold]")
        console.print("=" * 40)

        # ── Step 1: Validate API token ────────────────────────────────
        render_message("Step 1: Validating API token...", "info")

        if token:
            config.set_api_token(token)
        elif not config.has_credentials():
            if non_interactive:
                raise _NeedsInput("No API token configured — pass --token or set CLICKUP_API_KEY.")
            render_message("No API token found.", "warn")
            entered = typer.prompt("Enter your ClickUp API token")
            config.set_api_token(entered)

        async with ClickUpClient(config) as client:
            is_valid, message, user = await client.validate_auth()

            if not is_valid or user is None:
                render_message(f"Token validation failed: {message}", "error")
                if non_interactive:
                    raise _NeedsInput("Token rejected — re-run with a valid --token.")
                entered = typer.prompt("Enter a valid ClickUp API token")
                config.set_api_token(entered)
                async with ClickUpClient(config) as retry_client:
                    is_valid, message, user = await retry_client.validate_auth()
                    if not is_valid or user is None:
                        render_message(f"Still invalid: {message}", "error")
                        raise typer.Exit(1)
                    render_message(f"Authenticated as {user.username} ({user.email})", "success")
                    await _continue_setup(config, retry_client, user)
                    return

            render_message(f"Authenticated as {user.username} ({user.email})", "success")
            await _continue_setup(config, client, user)

    async def _continue_setup(config: Config, client: ClickUpClient, user: object) -> None:
        # ── Step 2: Choose team/workspace ──────────────────────────────
        render_message("\nStep 2: Selecting workspace...", "info")
        teams = await client.get_teams()

        if not teams:
            render_message("No workspaces found for this account.", "error")
            raise typer.Exit(1)

        if team_id is not None:
            team = next((t for t in teams if t.id == team_id), None)
            if team is None:
                render_error(f"Team/workspace ID {team_id!r} not found in this account.")
                raise typer.Exit(2)
            render_message(f"Selected workspace: {team.name} (via --team-id)", "success")
        elif len(teams) == 1:
            team = teams[0]
            render_message(f"Auto-selected workspace: {team.name} (only one available)", "success")
        else:
            team_items = [(t.id, t.name) for t in teams]
            chosen_id, _ = _pick_from_menu(
                team_items, "Select a workspace:", non_interactive=non_interactive, missing_flag="--team-id"
            )
            team = next(t for t in teams if t.id == chosen_id)

        config.set("default_team_id", team.id)

        # ── Step 3: Choose space ───────────────────────────────────────
        render_message("\nStep 3: Selecting space...", "info")
        spaces = await client.get_spaces(team.id)

        if not spaces:
            render_message("No spaces found in this workspace.", "error")
            raise typer.Exit(1)

        if space_id is not None:
            space = next((s for s in spaces if s.id == space_id), None)
            if space is None:
                render_error(f"Space ID {space_id!r} not found in workspace {team.name}.")
                raise typer.Exit(2)
            render_message(f"Selected space: {space.name} (via --space-id)", "success")
        elif len(spaces) == 1:
            space = spaces[0]
            render_message(f"Auto-selected space: {space.name} (only one available)", "success")
        else:
            space_items = [(s.id, s.name) for s in spaces]
            chosen_id, _ = _pick_from_menu(
                space_items, "Select a space:", non_interactive=non_interactive, missing_flag="--space-id"
            )
            space = next(s for s in spaces if s.id == chosen_id)

        config.set("default_space_id", space.id)

        # ── Step 4: Choose list ────────────────────────────────────────
        render_message("\nStep 4: Selecting default list...", "info")

        all_lists: list[ClickUpList] = await client.get_folderless_lists(space.id)
        folders = await client.get_folders(space.id)
        for folder in folders:
            folder_lists = await client.get_lists(folder.id)
            all_lists.extend(folder_lists)

        if list_id is not None:
            chosen_list_opt = next((lst for lst in all_lists if lst.id == list_id), None)
            if chosen_list_opt is None:
                render_error(f"List ID {list_id!r} not found in space {space.name}.")
                raise typer.Exit(2)
            config.set("default_list_id", chosen_list_opt.id)
            render_message(f"Selected list: {chosen_list_opt.name} (via --list-id)", "success")
        elif not all_lists:
            render_message("No lists found in this space.", "warn")
            console.print("You can set a default list later with: clickup config set default_list_id <ID>")
        else:
            table = Table(title="Available Lists", show_header=True)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="white")
            table.add_column("ID", style="dim")
            table.add_column("Tasks", style="green", justify="right")
            for idx, lst in enumerate(all_lists, 1):
                tc = str(lst.task_count) if lst.task_count is not None else "?"
                table.add_row(str(idx), lst.name, lst.id, tc)
            console.print(table)

            suggested = _suggest_most_active(all_lists)
            suggested_idx = all_lists.index(suggested) + 1 if suggested else 1

            if suggested:
                tc = suggested.task_count or 0
                console.print(
                    f"\n[bold]Suggested default:[/bold] {suggested.name} ({tc} tasks) [dim]-- highest task count[/dim]"
                )

            if non_interactive:
                if suggested is None:
                    raise _NeedsInput("No list selected and none can be auto-suggested — pass --list-id.")
                chosen_list = suggested
            else:
                use_suggested = typer.confirm(
                    f"Use {suggested.name} as default list?" if suggested else "Select a default list?",
                    default=True,
                )
                if use_suggested and suggested:
                    chosen_list = suggested
                else:
                    while True:
                        raw = typer.prompt("Enter list number", default=str(suggested_idx))
                        try:
                            choice = int(raw)
                            if 1 <= choice <= len(all_lists):
                                chosen_list = all_lists[choice - 1]
                                break
                        except ValueError:
                            pass
                        render_error(f"Please enter a number between 1 and {len(all_lists)}.")

            config.set("default_list_id", chosen_list.id)
            render_message(f"Default list set to: {chosen_list.name} (ID: {chosen_list.id})", "success")

        # ── Step 5: Smoke test ─────────────────────────────────────────
        render_message("\nStep 5: Running smoke test...", "info")
        default_list_id = config.get("default_list_id")
        if default_list_id:
            try:
                tasks = await client.get_tasks(default_list_id)
                sample = tasks[:5]
                if sample:
                    console.print(f"  Found {len(tasks)} tasks. Here are the first {len(sample)}:")
                    for t in sample:
                        status_str = t.status.status if t.status else "?"
                        console.print(f"    - {t.name} [{status_str}]")
                else:
                    console.print("  [dim]No tasks in this list yet.[/dim]")
            except Exception as e:
                render_message(f"Smoke test warning: {e}", "warn")

        # ── Done ───────────────────────────────────────────────────────
        console.print()
        render_message("You're set -- try `clickup task list` to see your tasks.", "success")

    try:
        run_async(_setup())
    except _NeedsInput as e:
        render_error(str(e))
        raise typer.Exit(2) from e
