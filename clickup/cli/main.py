"""Main CLI application entry point."""

import asyncio
import json
import sys

import click
import typer
from rich.console import Console
from rich.table import Table

from ..core import Config, get_provider, provider_name, provider_requires_credentials
from .commands import api, bulk, config, discover, folder, mock, task, templates, workspace
from .commands import list as list_cmd
from .commands import setup as setup_cmd
from .output import FormatChoice, error_payload, get_format, set_format

app = typer.Typer(
    name="clickup",
    help="ClickUp CLI - Task management from the command line.",
    add_completion=False,
    rich_markup_mode="rich",
    epilog="New here? Run [bold]clickup setup[/bold] to get started.",
)

_FORMAT_OPTION = typer.Option(
    None,
    "--format",
    help="Output format (json or table). Defaults to json; use --format table for human-friendly tables.",
    show_default=False,
)


@app.callback()
def _root_callback(
    output_format: FormatChoice | None = _FORMAT_OPTION,
) -> None:
    """ClickUp CLI - Task management from the command line."""
    # Reset format every invocation so module-level state doesn't bleed across
    # repeated CliRunner.invoke() calls in tests (and across long-running
    # processes that re-enter the CLI).
    set_format(output_format if output_format is not None else FormatChoice.json)


# -- Get started --------------------------------------------------------
app.add_typer(setup_cmd.app, name="setup", rich_help_panel="Get started")
app.add_typer(config.app, name="config", rich_help_panel="Get started")
app.add_typer(mock.app, name="mock", rich_help_panel="Get started")

# -- Task workflow -------------------------------------------------------
app.add_typer(task.app, name="task", rich_help_panel="Task workflow")

# -- Workspace navigation ------------------------------------------------
app.add_typer(workspace.app, name="workspace", rich_help_panel="Workspace navigation")
app.add_typer(list_cmd.app, name="list", rich_help_panel="Workspace navigation")
app.add_typer(folder.app, name="folder", rich_help_panel="Workspace navigation")
app.add_typer(discover.app, name="discover", rich_help_panel="Workspace navigation")

# -- Other ---------------------------------------------------------------
app.command("api", rich_help_panel="Other")(api.request)
app.add_typer(bulk.app, name="bulk", rich_help_panel="Other")
app.add_typer(templates.app, name="template", rich_help_panel="Other")

console = Console()


@app.command(rich_help_panel="Get started")
def status() -> None:
    """Show ClickUp connection status and current configuration."""

    async def _status() -> None:
        config_manager = Config()

        # Collect status data into a dict for both table and JSON output
        status_data: dict[str, object] = {}

        # Auth info
        api_token = config_manager.get_api_token()
        has_token = config_manager.has_credentials()

        if api_token and len(api_token) > 12:
            masked_token = f"{api_token[:8]}...{api_token[-4:]}"
        elif api_token:
            masked_token = "***"
        else:
            masked_token = None

        status_data["provider"] = provider_name(config_manager)
        status_data["api_token"] = masked_token or "Not configured"
        status_data["base_url"] = config_manager.get("base_url") or "N/A"

        # Defaults (raw IDs)
        default_team_id = config_manager.get("default_team_id")
        default_space_id = config_manager.get("default_space_id")
        default_list_id = config_manager.get("default_list_id")

        status_data["default_team_id"] = default_team_id
        status_data["default_space_id"] = default_space_id
        status_data["default_list_id"] = default_list_id

        # Resolve names for defaults and check auth
        auth_status = "No API token configured"
        auth_valid = False
        user_name: str | None = None
        user_email: str | None = None
        team_name: str | None = None
        space_name: str | None = None
        list_name: str | None = None

        can_query = has_token or not provider_requires_credentials(config_manager)
        if can_query:
            try:
                async with get_provider(config_manager) as client:
                    is_valid, message, user = await client.validate_auth()
                    if is_valid and user:
                        auth_valid = True
                        user_name = user.username
                        user_email = user.email
                        auth_status = f"Valid ({user.username}, {user.email})"

                        # Resolve team name
                        if default_team_id:
                            try:
                                team = await client.get_team(default_team_id)
                                team_name = team.name
                            except Exception:
                                pass

                        # Resolve space name
                        if default_space_id:
                            try:
                                space = await client.get_space(default_space_id)
                                space_name = space.name
                            except Exception:
                                pass

                        # Resolve list name
                        if default_list_id:
                            try:
                                lst = await client.get_list(default_list_id)
                                list_name = lst.name
                            except Exception:
                                pass

                        # Auto-detect singleton workspace if no default set
                        if not default_team_id:
                            try:
                                teams = await client.get_teams()
                                if len(teams) == 1:
                                    team_name = teams[0].name
                                    status_data["implicit_team_id"] = teams[0].id
                                    status_data["implicit_team_name"] = teams[0].name
                            except Exception:
                                pass
                    else:
                        auth_status = message
            except Exception as e:
                auth_status = f"Error: {e}"

        status_data["auth_status"] = auth_status
        status_data["auth_valid"] = auth_valid
        status_data["user_name"] = user_name
        status_data["user_email"] = user_email
        status_data["default_team_name"] = team_name
        status_data["default_space_name"] = space_name
        status_data["default_list_name"] = list_name

        # Determine if defaults are missing
        missing_defaults = not all([default_team_id, default_space_id, default_list_id])
        status_data["defaults_configured"] = not missing_defaults

        if get_format() == "json":
            console.print_json(json.dumps(status_data, default=str))
            return

        # ── Table output ──────────────────────────────────────────────
        table = Table(title="ClickUp Status", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Provider", status_data["provider"])

        # Auth section
        if auth_valid:
            table.add_row("Auth Status", "[green]Valid[/green]")
            table.add_row("User", str(user_name))
            table.add_row("Email", str(user_email))
        elif has_token:
            table.add_row("Auth Status", f"[red]{auth_status}[/red]")
        else:
            table.add_row("Auth Status", "[yellow]No API token configured[/yellow]")

        table.add_row("API Token", masked_token or "[red]Not configured[/red]")

        # Defaults section
        if default_team_id:
            label = f"{team_name} ({default_team_id})" if team_name else default_team_id
            table.add_row("Default Workspace", label)
        elif status_data.get("implicit_team_id"):
            implicit_name = status_data.get("implicit_team_name", "")
            table.add_row(
                "Default Workspace",
                f"[dim]{implicit_name} ({status_data['implicit_team_id']}) (auto-detected, not persisted)[/dim]",
            )
        else:
            table.add_row("Default Workspace", "[dim]Not set[/dim]")

        if default_space_id:
            label = f"{space_name} ({default_space_id})" if space_name else default_space_id
            table.add_row("Default Space", label)
        else:
            table.add_row("Default Space", "[dim]Not set[/dim]")

        if default_list_id:
            label = f"{list_name} ({default_list_id})" if list_name else default_list_id
            table.add_row("Default List", label)
        else:
            table.add_row("Default List", "[dim]Not set[/dim]")

        console.print(table)

        # Hints
        if not has_token:
            console.print(
                "\n[yellow]No API token configured. Set CLICKUP_API_KEY environment variable "
                "or use 'clickup config set-token <token>'.[/yellow]"
            )
        elif missing_defaults:
            console.print(
                "\n[yellow]Some defaults are not configured. Run `clickup setup run` to set them up.[/yellow]"
            )
        else:
            console.print("\nAll defaults configured. Use 'clickup task list' to see your tasks!")

    asyncio.run(_status())


@app.command(rich_help_panel="Other")
def version() -> None:
    """Show version information."""
    from . import __version__

    console.print(f"ClickUp Toolkit CLI v{__version__}")


async def async_main() -> None:
    """Async wrapper for CLI commands that need async support."""
    app()


def _wants_json_mode(argv: list[str]) -> bool:
    """Inspect argv for ``--format`` before Click parses it.

    The Typer root callback installs the format flag, but Click raises
    UsageError *during* argument parsing — before the callback runs — so we
    can't read ``get_format()`` here. JSON is the default per AGENT.md §2,
    so anything except an explicit ``--format table`` (or ``--format csv``,
    if ever supported) means JSON.
    """
    for i, arg in enumerate(argv):
        if arg == "--format" and i + 1 < len(argv):
            return argv[i + 1].lower() == "json"
        if arg.startswith("--format="):
            return arg.split("=", 1)[1].lower() == "json"
    return True


def _emit_click_error_envelope(exc: click.ClickException) -> None:
    """Render a click.ClickException as the canonical JSON error envelope.

    This closes the last gap from issue #29 P0 #2: Typer/Click usage errors
    (unknown subcommand, ``--limit abc``, missing required arg) used to emit
    Rich-formatted prose on stderr, bypassing the JSON envelope contract.
    The payload shape is shared with :func:`clickup.cli.output.render_error`
    via :func:`clickup.cli.output.error_payload`.
    """
    ctx = getattr(exc, "ctx", None)
    command = ctx.command_path if ctx is not None and ctx.command_path else None
    payload = error_payload(exc.format_message(), error_type=exc.__class__.__name__, command=command)
    typer.echo(json.dumps(payload), err=True)


def main() -> None:
    """Main entry point for the CLI.

    Runs the Typer app with ``standalone_mode=False`` so we can route Click's
    usage errors through the structured JSON envelope agents expect, instead
    of letting Click format them as Rich prose on stderr.
    """
    json_mode = _wants_json_mode(sys.argv[1:])
    try:
        # In non-standalone mode Click *returns* the exit code when a command
        # raises typer.Exit/ctx.exit() during invoke (it only lets the Exit
        # exception propagate in rarer paths). Dropping this return value
        # turned every application-level error into exit 0 — caught by the
        # round-3 agent study (Agent 15). Always propagate it.
        result = app(standalone_mode=False)
        if isinstance(result, int) and result != 0:
            sys.exit(result)
    except click.exceptions.UsageError as e:
        if json_mode:
            _emit_click_error_envelope(e)
        else:
            e.show()
        sys.exit(e.exit_code or 2)
    except click.exceptions.ClickException as e:
        # UsageError + its subclasses (NoSuchOption, BadParameter, etc.) are
        # caught above; this clause catches the other ClickException branch,
        # most realistically FileError.
        if json_mode:
            _emit_click_error_envelope(e)
        else:
            e.show()
        sys.exit(e.exit_code or 1)
    except click.exceptions.Abort:
        # Ctrl+C path; mirror Click's default exit code without the noisy
        # Rich traceback typer emits otherwise.
        sys.exit(1)
    except click.exceptions.Exit as e:
        # typer.Exit raises this with an explicit code; honor it.
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        # Match the JSON contract on stderr in JSON mode; Rich prose for humans.
        if json_mode:
            typer.echo(json.dumps(error_payload("Cancelled by user", error_type="KeyboardInterrupt")), err=True)
        else:
            console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(1)


if __name__ == "__main__":
    main()
