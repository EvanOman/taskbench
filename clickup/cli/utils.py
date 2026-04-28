"""Utility functions for CLI commands."""

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from contextlib import contextmanager
from typing import Any, TypeVar

T = TypeVar("T")


class _NullProgress:
    """No-op stand-in for rich.progress.Progress.

    The CLI is consumed primarily by AI agents and pipes; spinner frames on
    stdout corrupt --format json output and are useless to non-interactive
    callers. This class lets existing `with Progress(...): progress.add_task(...)`
    call sites compile and execute without producing any output.
    """

    def __enter__(self) -> "_NullProgress":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def add_task(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def update(self, *args: Any, **kwargs: Any) -> None:
        return None

    def advance(self, *args: Any, **kwargs: Any) -> None:
        return None


def Progress(*_args: Any, **_kwargs: Any) -> _NullProgress:  # noqa: N802
    """Drop-in shim for rich.progress.Progress that does nothing."""
    return _NullProgress()


def SpinnerColumn(*_args: Any, **_kwargs: Any) -> None:  # noqa: N802
    """Drop-in shim — accepts and discards any args."""
    return None


def TextColumn(*_args: Any, **_kwargs: Any) -> None:  # noqa: N802
    """Drop-in shim — accepts and discards any args."""
    return None


def BarColumn(*_args: Any, **_kwargs: Any) -> None:  # noqa: N802
    """Drop-in shim — accepts and discards any args."""
    return None


def TaskProgressColumn(*_args: Any, **_kwargs: Any) -> None:  # noqa: N802
    """Drop-in shim — accepts and discards any args."""
    return None


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


@contextmanager
def spinner(_description: str = "Working...") -> Any:
    """No-op spinner shim, kept so callers don't break."""
    yield _NullProgress()
