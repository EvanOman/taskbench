"""Shared helpers for CLI command modules."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, NoReturn

import typer
from rich.console import Console

from ..core import ClickUpError, Config, get_provider, provider_name, provider_requires_credentials
from .output import render_error

if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterator

    from ..core import TaskProvider

console = Console()


async def get_client() -> TaskProvider:
    """Get configured task provider."""
    config = Config()
    if provider_requires_credentials(config) and not config.has_credentials():
        render_error(
            "No ClickUp API token configured.",
            hint="Set CLICKUP_API_KEY in your environment (or .env), or run 'clickup config set-token <token>'.",
        )
        raise typer.Exit(2)
    return get_provider(config, console)


def usage_error(msg: str, hint: str | None = None) -> NoReturn:
    """Emit a usage error (render_error then exit 2)."""
    render_error(msg, hint=hint, error_type="UsageError")
    raise typer.Exit(2)


def resolve_list_id(list_id: str | None) -> str | None:
    """Resolve a list ID, expanding configured aliases.

    For the ``clickup`` provider, non-numeric values that are not configured
    aliases are rejected early with a helpful usage error (exit 2) instead of
    being forwarded to the API where they produce an opaque failure.

    Other providers (``json``, ``planka``) use non-numeric list IDs
    legitimately, so the strictness is skipped for them.  The check is also
    skipped when the clickup provider has no credentials configured, since
    the request will fail later at the ``get_client`` stage anyway (and this
    avoids false positives in test environments where ``get_client`` is mocked).
    """
    config = Config()
    resolved = config.resolve_list_id(list_id)
    # If the caller passed a value AND it came back unchanged AND it isn't
    # numeric, that means it didn't match any alias.  For the ClickUp SaaS
    # provider, numeric IDs are required — surface the mismatch now.
    # The credentials gate prevents false positives when get_client is mocked.
    is_clickup = provider_name(config) == "clickup" and config.has_credentials()
    if list_id is not None and resolved == list_id and not list_id.isdigit() and is_clickup:
        aliases: dict[str, str] = config.get("default_lists") or {}
        alias_names = ", ".join(sorted(aliases.keys())) if aliases else "(none)"
        usage_error(
            f"Unknown list or alias '{list_id}'. Configured aliases: {alias_names}.",
            hint="Run 'clickup config get default_lists' to see aliases, or 'clickup setup run' to configure them.",
        )
    return resolved


def split_csv(value: str | None) -> list[str]:
    """Split a comma-separated CLI value, trimming whitespace and rejecting empties."""
    if value is None:
        return []
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part for part in parts):
        usage_error(f"Error: empty value in comma-separated argument '{value}'.")
    return parts


def resolve_list_ids(list_id: str | None, *, all_lists: bool = False) -> list[str]:
    """Resolve one or more list IDs/aliases from CLI input."""
    config = Config()
    if all_lists:
        aliases: dict[str, str] = config.get("default_lists") or {}
        if not aliases:
            usage_error(
                "Error: --all-lists queries the configured default_lists aliases, and none are configured.",
                hint=(
                    "Configure aliases with 'clickup config set default_lists "
                    '\'{"inbox": "<list-id>", ...}\'\' — or use task search / task mine for a '
                    "workspace-wide query."
                ),
            )
        return list(aliases.values())

    raw_values = split_csv(list_id)
    if not raw_values:
        resolved = resolve_list_id(None)
        return [resolved] if resolved else []
    return [resolved for raw in raw_values if (resolved := resolve_list_id(raw))]


def require_list_id(list_id: str | None) -> str:
    """Resolve a list ID and exit 2 if none is available."""
    resolved = resolve_list_id(list_id)
    if resolved:
        return resolved
    usage_error(
        "Error: No list ID provided and no default list configured.",
        hint=(
            "Use --list-id or set a default with 'clickup config set default_list_id <id>' "
            "(or 'clickup setup run --auto'). Find IDs with 'clickup discover hierarchy', "
            "or query across lists with 'clickup task search' / 'clickup task mine'."
        ),
    )


async def resolve_workspace_id(client: TaskProvider, workspace_id: str | None) -> str:
    """Resolve workspace ID from arg, config, or single-workspace auto-detect."""
    if workspace_id:
        return workspace_id
    config = Config()
    default = config.get("default_team_id")
    if default:
        return default
    teams = await client.get_teams()
    if len(teams) == 1:
        return teams[0].id
    if not teams:
        render_error("Error: No workspaces found for this account.")
        raise typer.Exit(1)
    render_error("Error: Multiple workspaces found. Please specify --workspace-id.")
    raise typer.Exit(1)


@contextlib.contextmanager
def handle_clickup_errors() -> Iterator[None]:
    """Catch ClickUpError and convert to a rendered error + Exit(1)."""
    try:
        yield
    except ClickUpError as e:
        render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
        raise typer.Exit(1) from e


async def gather_bounded(
    coros: list[Coroutine[Any, Any, Any]],
    limit: int = 5,
) -> list[Any]:
    """Run coroutines concurrently with bounded parallelism, preserving input order.

    Each coroutine is wrapped so that at most ``limit`` run at the same time.
    Results are returned in the same order as the input list, regardless of
    completion order. Exceptions are NOT raised — they are returned in the
    result list so callers can inspect per-item success/failure.
    """
    semaphore = asyncio.Semaphore(limit)

    async def _wrap(coro: Coroutine[Any, Any, Any]) -> Any:
        async with semaphore:
            return await coro

    return list(await asyncio.gather(*(_wrap(c) for c in coros), return_exceptions=True))
