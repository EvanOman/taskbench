"""Configuration management commands."""

import typer
from rich.console import Console
from rich.table import Table

from ...core import ClickUpClient, Config
from ...core.config import _CREDENTIAL_KEYS, _DEFAULT_KEYS, is_known_key
from ..output import render_error
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
    """Set a configuration value.

    Tip: set `default_list_id` to skip --list-id on every task command.
    """
    config = Config()
    try:
        config.set(key, value)
        console.print(f"✅ Set {key} = {value}")
    except ValueError as e:
        render_error(f"Error: {e}")
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
def show_config(
    show_all: bool = typer.Option(False, "--all", "-a", help="Include unknown/custom keys"),
) -> None:
    """Show all configuration values, grouped into sections.

    By default, unknown/custom keys are hidden. Use --all to see them.
    The api_token is always fully masked.
    """
    config = Config()
    data = config.config.model_dump(exclude_none=True)

    # Build section buckets
    credentials: dict[str, object] = {}
    defaults: dict[str, object] = {}
    other: dict[str, object] = {}
    unknown: dict[str, object] = {}

    for key, val in data.items():
        if key in _CREDENTIAL_KEYS:
            credentials[key] = val
        elif key in _DEFAULT_KEYS:
            defaults[key] = val
        elif is_known_key(key):
            other[key] = val
        else:
            unknown[key] = val

    def _mask(key: str, val: object) -> str:
        """Mask sensitive values for display."""
        if key == "api_token":
            return "********"  # fully masked
        if key in ("client_secret",):
            return "***"
        if key == "client_id" and isinstance(val, str) and len(val) > 12:
            return f"{val[:8]}...{val[-4:]}"
        return str(val)

    def _render_section(title: str, items: dict[str, object]) -> None:
        if not items:
            return
        table = Table(title=title, show_header=True, title_style="bold")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for k, v in items.items():
            table.add_row(k, _mask(k, v))
        console.print(table)
        console.print()

    _render_section("Credentials", credentials)
    _render_section("Defaults", defaults)
    _render_section("Other", other)

    if show_all and unknown:
        _render_section("Unknown / Custom", unknown)
    elif unknown:
        console.print(f"[dim]{len(unknown)} unknown key(s) hidden. Use --all to show them.[/dim]")


@app.command("set-default-list")
def set_default_list(
    name: str = typer.Argument(..., help="Alias name for the list (e.g. 'omegapoint')"),
    list_id: str | None = typer.Argument(None, help="Numeric ClickUp list ID to map to"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove the alias instead of adding"),
) -> None:
    """Add or remove a named alias for a ClickUp list ID.

    Examples:

        clickup config set-default-list omegapoint 901315992466

        clickup config set-default-list --remove omegapoint

    Tip: set `default_list_id` to skip --list-id on every task command.
    """
    config = Config()
    aliases: dict[str, str] = config.get("default_lists") or {}

    if remove:
        if name not in aliases:
            console.print(f"[yellow]Alias '{name}' not found in default_lists.[/yellow]")
            raise typer.Exit(1)
        del aliases[name]
        config.set("default_lists", aliases)
        console.print(f"✅ Removed alias '{name}'")
        return

    if list_id is None:
        render_error("Error: list_id is required when adding an alias.")
        raise typer.Exit(1)

    aliases[name] = list_id
    config.set("default_lists", aliases)
    console.print(f"✅ Alias '{name}' -> {list_id}")


@app.command("clean")
def clean_config(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview keys that would be removed without writing"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to actually remove keys. No interactive prompt.",
    ),
) -> None:
    """Prune unknown/garbage keys from the persisted config.

    By default, removes any top-level keys not in the known-key list.
    Use --dry-run to preview, then re-run with --force/--yes to apply.
    """
    config = Config()
    unknown = config.unknown_keys()

    if not unknown:
        console.print("[green]Config is clean -- no unknown keys found.[/green]")
        return

    table = Table(title="Unknown keys to remove", show_header=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="yellow")
    for k, v in unknown.items():
        table.add_row(k, str(v))
    console.print(table)

    if dry_run:
        console.print(f"\n[dim]Dry run: {len(unknown)} key(s) would be removed.[/dim]")
        return

    if not force:
        render_error(f"Refusing to remove {len(unknown)} key(s) without --force/--yes (use --dry-run to preview).")
        raise typer.Exit(2)

    config.remove_keys(set(unknown.keys()))
    console.print(f"[green]✅ Removed {len(unknown)} key(s).[/green]")


@app.command("reset")
def reset_config(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        "-y",
        help="Required to confirm reset. No interactive prompt.",
    ),
) -> None:
    """Reset configuration to defaults."""
    if not force:
        render_error("Refusing to reset without --force/--yes (this CLI never prompts).")
        raise typer.Exit(2)
    config = Config()
    config.config_path.unlink(missing_ok=True)
    console.print("✅ Configuration reset to defaults")


@app.command("validate")
def validate_auth() -> None:
    """Validate API credentials by checking user info."""

    async def _validate() -> None:
        config = Config()
        if not config.has_credentials():
            render_error("❌ No API credentials configured")
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
                    render_error(f"{message}")
                    raise typer.Exit(1)

        except Exception as e:
            render_error(f"❌ Error validating credentials: {str(e)}")
            raise typer.Exit(1) from e

    run_async(_validate())


@app.command("whoami")
def whoami() -> None:
    """Show current authenticated user and configured defaults."""

    async def _whoami() -> None:
        config = Config()
        if not config.has_credentials():
            render_error("No API credentials configured.")
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

                default_team = config.get("default_team_id")
                default_space = config.get("default_space_id")
                default_list = config.get("default_list_id")

                table.add_row("Default Team ID", default_team or "[dim]Not set[/dim]")
                table.add_row("Default Space ID", default_space or "[dim]Not set[/dim]")
                table.add_row("Default List ID", default_list or "[dim]Not set[/dim]")

                console.print(table)

        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_whoami())
