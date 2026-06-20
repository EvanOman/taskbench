"""Local mock provider commands."""

from pathlib import Path

import typer
from rich.console import Console

from ...core import Config
from ...core.json_provider import default_store_path, write_seed_store
from ..output import get_format, render_error, render_kv

app = typer.Typer(help="Local JSON mock backend")
console = Console()


@app.command("init")
def init_mock(
    path: str | None = typer.Option(None, "--path", help="JSON store path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing store"),
    configure: bool = typer.Option(True, "--configure/--no-configure", help="Set config to use this JSON provider"),
) -> None:
    """Create a seeded local JSON backend for offline CLI testing."""
    store_path = Path(path).expanduser() if path else default_store_path()
    try:
        write_seed_store(store_path, force=force)
    except FileExistsError as e:
        render_error(f"Error: mock store already exists at {store_path}. Pass --force to overwrite it.")
        raise typer.Exit(2) from e

    if configure:
        config = Config()
        config.set("provider", "json")
        config.set("json_store_path", str(store_path))
        config.set("default_team_id", "team_mock")
        config.set("default_space_id", "space_ops")
        config.set("default_list_id", "list_inbox")
        config.set("default_lists", {"inbox": "list_inbox", "active": "list_active"})

    data = {
        "provider": "json" if configure else None,
        "json_store_path": str(store_path),
        "default_team_id": "team_mock" if configure else None,
        "default_space_id": "space_ops" if configure else None,
        "default_list_id": "list_inbox" if configure else None,
        "default_lists": {"inbox": "list_inbox", "active": "list_active"} if configure else None,
    }
    if get_format() == "json":
        render_kv(data)
        return
    console.print(f"Mock store initialized at {store_path}")
