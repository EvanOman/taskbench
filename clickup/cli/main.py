"""Main CLI application entry point."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from ..core import ClickUpClient, Config
from .commands import bulk, config, discover, task, templates, workspace
from .commands import list as list_cmd
from .output import FormatChoice, set_format

app = typer.Typer(
    name="clickup",
    help="🎯 ClickUp CLI - Powerful task management from the command line",
    add_completion=False,
    rich_markup_mode="rich",
)


_FORMAT_OPTION = typer.Option(
    None,
    "--format",
    help="Output format (table or json)",
    show_default=False,
)


@app.callback()
def _root_callback(
    output_format: FormatChoice | None = _FORMAT_OPTION,
) -> None:
    """ClickUp CLI - Powerful task management from the command line."""
    if output_format is not None:
        set_format(output_format)


# Add subcommands
app.add_typer(task.app, name="task", help="Task management commands")
app.add_typer(config.app, name="config", help="Configuration commands")
app.add_typer(workspace.app, name="workspace", help="Workspace management commands")
app.add_typer(list_cmd.app, name="list", help="List management commands")
app.add_typer(bulk.app, name="bulk", help="Bulk operations and import/export")
app.add_typer(templates.app, name="template", help="Template management")
app.add_typer(discover.app, name="discover", help="Discover and navigate ClickUp hierarchy")

console = Console()


@app.command()
def status() -> None:
    """Show ClickUp connection status and current configuration."""

    async def _status() -> None:
        config_manager = Config()

        table = Table(title="ClickUp Status", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        # Check API token (primary auth method)
        api_token = config_manager.get_api_token()
        has_token = config_manager.has_credentials()

        if api_token:
            # Mask the token for display
            if len(api_token) > 12:
                masked_token = f"{api_token[:8]}...{api_token[-4:]}"
            else:
                masked_token = "***"
            table.add_row("API Token", masked_token)
        else:
            table.add_row("API Token", "[red]Not configured[/red]")

        base_url = config_manager.get("base_url") or "N/A"
        table.add_row("Base URL", base_url)
        table.add_row("Default Team", config_manager.get("default_team_id") or "[dim]None[/dim]")
        table.add_row("Default Space", config_manager.get("default_space_id") or "[dim]None[/dim]")
        table.add_row("Default List", config_manager.get("default_list_id") or "[dim]None[/dim]")
        output_format = config_manager.get("output_format") or "json"
        table.add_row("Output Format", output_format)

        # Test authentication if API token is available
        if has_token:
            try:
                async with ClickUpClient(config_manager) as client:
                    is_valid, message, user = await client.validate_auth()
                    if is_valid and user:
                        table.add_row("Auth Status", f"[green]✅ Valid ({user.username})[/green]")
                    else:
                        table.add_row("Auth Status", f"[red]❌ {message}[/red]")
            except Exception as e:
                table.add_row("Auth Status", f"[red]❌ Error: {str(e)}[/red]")
        else:
            table.add_row("Auth Status", "[yellow]⚠️  No API token configured[/yellow]")

        console.print(table)

        if not has_token:
            console.print(
                "\n[yellow]⚠️  No API token configured. Set CLICKUP_API_KEY environment variable "
                "or use 'clickup config set-token <token>'.[/yellow]"
            )
            console.print("💡 Get your API token from ClickUp Settings > Apps > API Token")
        else:
            console.print(
                "\n💡 Need folder or list IDs? Use '[bold]clickup discover ids[/bold]' to explore your workspace!"
            )

    asyncio.run(_status())


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__

    console.print(f"ClickUp Toolkit CLI v{__version__}")


async def async_main() -> None:
    """Async wrapper for CLI commands that need async support."""
    app()


def main() -> None:
    """Main entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    main()
