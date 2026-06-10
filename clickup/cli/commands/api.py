"""Raw ClickUp API escape hatch."""

import json
from typing import Any, NoReturn

import typer
from rich.console import Console

from ...core import ClickUpError, Config, TaskProvider, get_provider, provider_requires_credentials
from ..output import render_error, render_kv
from ..utils import run_async

console = Console()

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_PARAM_OPTION = typer.Option(None, "--param", "-p", help="Query parameter as key=value")


async def get_client() -> TaskProvider:
    """Get configured task provider."""
    config = Config()
    if provider_requires_credentials(config) and not config.has_credentials():
        render_error(
            "Error: No ClickUp API token configured. Set CLICKUP_API_KEY in your "
            "environment (or .env), or run 'clickup config set-token <token>'."
        )
        raise typer.Exit(1)
    return get_provider(config, console)


def _usage_error(msg: str) -> NoReturn:
    render_error(msg)
    raise typer.Exit(2)


def _parse_json_data(data: str | None) -> Any:
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        _usage_error(f"Error: --data must be valid JSON ({e.msg}).")


def _parse_params(params: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in params or []:
        if "=" not in item:
            _usage_error(f"Error: --param value must be key=value, got {item!r}.")
        key, value = item.split("=", 1)
        if not key:
            _usage_error("Error: --param key cannot be empty.")
        if key in parsed:
            existing = parsed[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                parsed[key] = [existing, value]
        else:
            parsed[key] = value
    return parsed


def request(
    method: str = typer.Argument(..., help="HTTP method: GET, POST, PUT, PATCH, DELETE"),
    endpoint: str = typer.Argument(..., help="ClickUp API path, e.g. /task/abc123"),
    data: str | None = typer.Option(None, "--data", "-d", help="JSON request body"),
    params: list[str] | None = _PARAM_OPTION,
) -> None:
    """Call a ClickUp API endpoint not wrapped by a typed command."""

    async def _request() -> None:
        method_to_use = method.upper()
        if method_to_use not in _ALLOWED_METHODS:
            _usage_error(f"Error: unsupported method {method!r}. Use one of: {', '.join(sorted(_ALLOWED_METHODS))}.")

        json_body = _parse_json_data(data)
        query_params = _parse_params(params)
        request_kwargs: dict[str, Any] = {}
        if json_body is not None:
            request_kwargs["json"] = json_body
        if query_params:
            request_kwargs["params"] = query_params

        try:
            async with await get_client() as client:
                result = await client.raw_request(method_to_use, endpoint, **request_kwargs)
                render_kv(result)
        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}", error_type=type(e).__name__)
            raise typer.Exit(1) from e

    run_async(_request())
