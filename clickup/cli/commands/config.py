"""Configuration management commands."""

import typer
from rich.console import Console
from rich.table import Table

from ...core import ClickUpClient, Config
from ..utils import run_async

app = typer.Typer(help="Configuration management")
console = Console()


@app.command("set-client-id")
def set_client_id(client_id: str = typer.Argument(..., help="ClickUp Client ID")) -> None:
    """Set your ClickUp Client ID."""
    config = Config()
    config.set_client_id(client_id)
    console.print("✅ Client ID configured successfully!")


@app.command("set-client-secret")
def set_client_secret(client_secret: str = typer.Argument(..., help="ClickUp Client Secret")) -> None:
    """Set your ClickUp Client Secret."""
    config = Config()
    config.set_client_secret(client_secret)
    console.print("✅ Client Secret configured successfully!")


@app.command("set-token")
def set_api_token(api_token: str = typer.Argument(..., help="ClickUp API Token")) -> None:
    """Set your ClickUp API Token."""
    config = Config()
    config.set_api_token(api_token)
    console.print("✅ API Token configured successfully!")


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
) -> None:
    """Set a configuration value."""
    config = Config()
    try:
        config.set(key, value)
        console.print(f"✅ Set {key} = {value}")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("get")
def get_config(key: str = typer.Argument(..., help="Configuration key")) -> None:
    """Get a configuration value."""
    config = Config()
    value = config.get(key)
    if value is not None:
        console.print(f"{key} = {value}")
    else:
        console.print(f"[yellow]{key} is not set[/yellow]")


@app.command("show")
def show_config() -> None:
    """Show all configuration values."""
    config = Config()

    table = Table(title="ClickUp Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, config_value in config.config.model_dump(exclude_none=True).items():
        display_value = config_value
        if key in ("client_secret", "api_token") and config_value:
            display_value = "***"
        elif key == "client_id" and config_value:
            display_value = f"{config_value[:8]}...{config_value[-4:]}" if len(config_value) > 12 else "***"
        table.add_row(key, str(display_value))

    console.print(table)


@app.command("reset")
def reset_config() -> None:
    """Reset configuration to defaults."""
    if typer.confirm("Are you sure you want to reset all configuration?"):
        config = Config()
        config.config_path.unlink(missing_ok=True)
        console.print("✅ Configuration reset to defaults")


@app.command("validate")
def validate_auth() -> None:
    """Validate API credentials by checking user info."""

    async def _validate() -> None:
        config = Config()
        if not config.has_credentials():
            console.print("[red]❌ No API credentials configured[/red]")
            console.print(
                "Set CLICKUP_API_KEY in your environment (or .env), or run 'clickup config set-token <token>'."
            )
            raise typer.Exit(1)

        try:
            async with ClickUpClient(config) as client:
                is_valid, message, user = await client.validate_auth()

                if is_valid:
                    console.print(f"[green]{message}[/green]")
                    if user:
                        # Show user details
                        table = Table(title="User Information", show_header=False)
                        table.add_column("Field", style="cyan", width=15)
                        table.add_column("Value", style="white")

                        table.add_row("ID", str(user.id))
                        table.add_row("Username", user.username)
                        table.add_row("Email", user.email or "N/A")
                        table.add_row("Color", user.color or "N/A")
                        table.add_row("Profile Picture", "✅" if user.profilePicture else "❌")

                        console.print(table)
                else:
                    console.print(f"[red]{message}[/red]")
                    raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]❌ Error validating credentials: {str(e)}[/red]")
            raise typer.Exit(1) from e

    run_async(_validate())


# ===== OWNED BY E: =====
@app.command("whoami")
def whoami() -> None:
    """Show current authenticated user and configured defaults."""

    async def _whoami() -> None:
        config = Config()
        if not config.has_credentials():
            console.print("[red]No API credentials configured.[/red]")
            console.print("Set CLICKUP_API_KEY or run 'clickup setup run'.")
            raise typer.Exit(1)

        try:
            async with ClickUpClient(config) as client:
                user = await client.get_user()

                table = Table(title="Who Am I", show_header=False)
                table.add_column("Field", style="cyan", width=20)
                table.add_column("Value", style="white")

                table.add_row("User ID", str(user.id))
                table.add_row("Username", user.username)
                table.add_row("Email", user.email or "N/A")
                table.add_row("Color", user.color or "N/A")

                # Show configured defaults
                default_team = config.get("default_team_id")
                default_space = config.get("default_space_id")
                default_list = config.get("default_list_id")

                table.add_row("Default Team ID", default_team or "[dim]Not set[/dim]")
                table.add_row("Default Space ID", default_space or "[dim]Not set[/dim]")
                table.add_row("Default List ID", default_list or "[dim]Not set[/dim]")

                console.print(table)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

    run_async(_whoami())


# ===== END OWNED BY E =====
