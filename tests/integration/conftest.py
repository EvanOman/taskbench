"""Shared fixtures and helpers for integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from clickup.cli.output import set_format


@pytest.fixture(autouse=True)
def _reset_format():
    """The global format state bleeds across test invocations — reset it."""
    set_format("table")
    yield
    set_format("table")


def make_mock_ctx(client: AsyncMock) -> AsyncMock:
    """Wrap an AsyncMock client in an async-context-manager Mock.

    Replaces the copy-pasted ``_ctx()`` helper that appeared in every file.
    """
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


def named_mock(**kw) -> Mock:
    """Build a Mock where ``.name`` is a real string.

    ``Mock(name=...)`` sets the mock's internal label, not a normal attribute.
    This helper pops ``name`` and assigns it after construction.
    """
    name = kw.pop("name", None)
    m = Mock(**kw)
    if name is not None:
        m.name = name
    return m


def make_mock_client() -> AsyncMock:
    """Build a fresh AsyncMock suitable for use as a ClickUp client.

    Returns the mock directly — wrap with ``make_mock_ctx()`` when a
    context-manager is needed.
    """
    return AsyncMock()
