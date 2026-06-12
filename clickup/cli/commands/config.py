"""Configuration management commands."""

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...core import Config, get_provider, provider_requires_credentials
from ...core.config import _CREDENTIAL_KEYS, _DEFAULT_KEYS, is_known_key
from ..output import _print_json, get_format, render_error, render_kv, render_message, render_user
from ..utils import run_async

app = typer.Typer(help="Configuration management")
console = Console()


@app.command("set-client-id")
def set_client_id(client_id: str = typer.Argument(..., help="ClickUp Client ID")) -> None:
    """Set your ClickUp Client ID."""
    config = Config()
    config.set_client_id(client_id)
    render_kv({"key": "client_id", "value": client_id})
    render_message("Client ID configured successfully!", level="success")


@app.command("set-client-secret")
def set_client_secret(client_secret: str = typer.Argument(..., help="ClickUp Client Secret")) -> None:
    """Set your ClickUp Client Secret."""
    config = Config()
    config.set_client_secret(client_secret)
    render_kv({"key": "client_secret", "value": "***"})
    render_message("Client Secret configured successfully!", level="success")


@app.command("set-token")
def set_api_token(api_token: str = typer.Argument(..., help="ClickUp API Token")) -> None:
    """Set your ClickUp API Token."""
    config = Config()
    config.set_api_token(api_token)
    render_kv({"key": "api_token", "value": "********"})
    render_message("API Token configured successfully!", level="success")


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
        render_kv({"key": key, "value": value})
        render_message(f"Set {key} = {value}", level="success")
    except ValueError as e:
        render_error(f"Error: {e}")
        raise typer.Exit(1) from e


@app.command("get")
def get_config(key: str = typer.Argument(..., help="Configuration key")) -> None:
    """Get a configuration value."""
    config = Config()
    value = config.get(key)
    if value is not None:
        render_kv({"key": key, "value": value})
    else:
        render_kv({"key": key, "value": None})
        render_message(f"{key} is not set", level="info")


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
        if key == "api_token":
            s = str(val)
            if len(s) > 8:
                return f"{s[:4]}...{s[-4:]}"
            return "********"
        if key in ("client_secret",):
            return "***"
        if key == "client_id" and isinstance(val, str) and len(val) > 12:
            return f"{val[:8]}...{val[-4:]}"
        return str(val)

    if get_format() == "json":
        masked: dict[str, object] = {}
        for k, v in {**credentials, **defaults, **other}.items():
            masked[k] = _mask(k, v)
        if show_all and unknown:
            for k, v in unknown.items():
                masked[k] = _mask(k, v)
        _print_json(masked)
        return

    def _render_section(title: str, items: dict[str, object]) -> None:
        if not items:
            return
        table = Table(title=title, show_header=True, title_style="bold")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for k, v in items.items():
            table.add_row(escape(k), escape(_mask(k, v)))
        console.print(table)
        console.print()

    _render_section("Credentials", credentials)
    _render_section("Defaults", defaults)
    _render_section("Other", other)

    if show_all and unknown:
        _render_section("Unknown / Custom", unknown)
    elif unknown:
        render_message(f"{len(unknown)} unknown key(s) hidden. Use --all to show them.", level="info")


def _alias_impl(
    name: str | None = None,
    list_id: str | None = None,
    remove: bool = False,
) -> None:
    """Shared implementation for config alias / set-default-list."""
    config = Config()
    aliases: dict[str, str] = config.get("default_lists") or {}

    # No arguments at all → list the current alias map.
    if name is None and not remove:
        rows = [{"alias": k, "list_id": v} for k, v in sorted(aliases.items())]
        if get_format() == "json":
            _print_json({"data": rows, "count": len(rows)})
        else:
            if not rows:
                render_message("No aliases configured.", level="info")
                return
            table = Table(title="List Aliases", show_header=True)
            table.add_column("Alias", style="cyan")
            table.add_column("List ID", style="green")
            for row in rows:
                table.add_row(escape(row["alias"]), escape(row["list_id"]))
            console.print(table)
        return

    # name is required for add/remove from here on.
    if name is None:
        render_error("Error: alias name is required when using --remove.")
        raise typer.Exit(2)

    if remove:
        if name not in aliases:
            render_error(f"Alias '{name}' not found in default_lists.")
            raise typer.Exit(1)
        del aliases[name]
        config.set("default_lists", aliases)
        render_kv({"action": "removed", "alias": name})
        render_message(f"Removed alias '{name}'", level="success")
        return

    if list_id is None:
        render_error("Error: list_id is required when adding an alias.")
        raise typer.Exit(1)

    aliases[name] = list_id
    config.set("default_lists", aliases)
    render_kv({"action": "added", "alias": name, "list_id": list_id})
    render_message(f"Alias '{name}' -> {list_id}", level="success")


@app.command("alias")
def config_alias(
    name: str | None = typer.Argument(None, help="Alias name for the list (e.g. 'omegapoint')"),
    list_id: str | None = typer.Argument(None, help="Numeric ClickUp list ID to map to"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove the alias instead of adding"),
) -> None:
    """Add, remove, or list named aliases for ClickUp list IDs.

    With no arguments, lists all configured aliases. Pass NAME LIST_ID to add
    an alias, or NAME --remove to delete one.

    Examples:

        clickup config alias                              # list all
        clickup config alias omegapoint 901315992466      # add
        clickup config alias --remove omegapoint          # remove

    Tip: set `default_list_id` to skip --list-id on every task command.
    """
    _alias_impl(name=name, list_id=list_id, remove=remove)


@app.command("set-default-list", hidden=True)
def set_default_list(
    name: str = typer.Argument(..., help="Alias name for the list (e.g. 'omegapoint')"),
    list_id: str | None = typer.Argument(None, help="Numeric ClickUp list ID to map to"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove the alias instead of adding"),
) -> None:
    """Add or remove a named alias for a ClickUp list ID (back-compat; prefer 'config alias')."""
    _alias_impl(name=name, list_id=list_id, remove=remove)


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
        render_kv({"unknown_keys": 0})
        render_message("Config is clean -- no unknown keys found.", level="success")
        return

    if dry_run:
        render_kv({"dry_run": True, "would_remove": len(unknown), "keys": list(unknown.keys())})
        render_message(f"Dry run: {len(unknown)} key(s) would be removed.", level="info")
        return

    if not force:
        render_error(
            f"Refusing to remove {len(unknown)} key(s) without --force/--yes (use --dry-run to preview).",
            error_type="UsageError",
        )
        raise typer.Exit(2)

    config.remove_keys(set(unknown.keys()))
    render_kv({"removed": len(unknown), "keys": list(unknown.keys())})
    render_message(f"Removed {len(unknown)} key(s).", level="success")


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
        render_error("Refusing to reset without --force/--yes (this CLI never prompts).", error_type="UsageError")
        raise typer.Exit(2)
    config = Config()
    config.config_path.unlink(missing_ok=True)
    render_kv({"action": "reset"})
    render_message("Configuration reset to defaults", level="success")


@app.command("validate")
def validate_auth() -> None:
    """Validate API credentials by checking user info."""

    async def _validate() -> None:
        config = Config()
        if provider_requires_credentials(config) and not config.has_credentials():
            render_error(
                "❌ No API credentials configured",
                hint="Set CLICKUP_API_KEY in your environment (or .env), or run 'clickup config set-token <token>'.",
            )
            raise typer.Exit(1)

        try:
            async with get_provider(config) as client:
                is_valid, message, user = await client.validate_auth()

                if is_valid:
                    render_message(message, level="success")
                    if user:
                        render_user(user)
                else:
                    render_error(f"{message}")
                    raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            render_error(f"Error validating credentials: {str(e)}")
            raise typer.Exit(1) from e

    run_async(_validate())


@app.command("whoami")
def whoami() -> None:
    """Show current authenticated user and configured defaults."""

    async def _whoami() -> None:
        config = Config()
        if provider_requires_credentials(config) and not config.has_credentials():
            render_error(
                "No API credentials configured.",
                hint="Set CLICKUP_API_KEY or run 'clickup setup run'.",
            )
            raise typer.Exit(1)

        try:
            async with get_provider(config) as client:
                user = await client.get_user()

                default_team = config.get("default_team_id")
                default_space = config.get("default_space_id")
                default_list = config.get("default_list_id")

                if get_format() == "json":
                    _print_json(
                        {
                            "user_id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "color": user.color,
                            "default_team_id": default_team,
                            "default_space_id": default_space,
                            "default_list_id": default_list,
                        }
                    )
                    return

                table = Table(title="Who Am I", show_header=False)
                table.add_column("Field", style="cyan", width=20)
                table.add_column("Value", style="white")

                table.add_row("User ID", str(user.id))
                table.add_row("Username", escape(user.username))
                table.add_row("Email", escape(user.email) if user.email else "N/A")
                table.add_row("Color", user.color or "N/A")
                table.add_row("Default Team ID", default_team or "[dim]Not set[/dim]")
                table.add_row("Default Space ID", default_space or "[dim]Not set[/dim]")
                table.add_row("Default List ID", default_list or "[dim]Not set[/dim]")

                console.print(table)

        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_whoami())
