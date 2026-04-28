"""Utility functions for CLI commands."""

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, TypeVar

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:  # noqa: UP047
    """
    Helper to run async functions in sync context.

    Handles both cases:
    - Normal execution: uses asyncio.run()
    - Testing with pytest-asyncio: runs in new thread with new event loop
    """

    def _run_in_new_loop() -> T:
        """Run coroutine in a completely new event loop."""
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    try:
        # Try to get current loop
        asyncio.get_running_loop()

        # If we get here, there's already a loop running (test environment)
        # Run in a separate thread with new loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_in_new_loop)
            return future.result(timeout=30)  # 30 second timeout

    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                # Fallback to thread approach
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_run_in_new_loop)
                    return future.result(timeout=30)
            else:
                raise


# ---------------------------------------------------------------------------
# Spinner helper — fixes bleed-through artifacts
# ---------------------------------------------------------------------------

# A stderr-only console so spinner frames never pollute stdout (where JSON
# and table output goes).  ``transient=True`` on the Progress widget erases
# the spinner line when the context manager exits, preventing leftover
# artefacts even when stderr and stdout share the same terminal.

_stderr_console = Console(stderr=True, force_terminal=True)


def spinner(description: str = "Working...") -> Progress:
    """Return a ``rich.progress.Progress`` spinner that writes to *stderr*
    and auto-cleans on exit (``transient=True``).

    Usage::

        with spinner("Fetching tasks...") as progress:
            progress.add_task("Fetching tasks...", total=None)
            result = await do_work()
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=_stderr_console,
        transient=True,
    )
