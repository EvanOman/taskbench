"""Unit tests for clickup.cli.shared helpers."""

from __future__ import annotations

import asyncio

import pytest
import typer

from clickup.cli.shared import gather_bounded, get_client, handle_clickup_errors, require_list_id
from clickup.core.exceptions import ClickUpError


class TestRequireListId:
    def test_returns_resolved_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        from clickup.core import Config

        Config().set("default_list_id", "L42")
        assert require_list_id(None) == "L42"

    def test_explicit_id_passes_through(self):
        assert require_list_id("explicit123") == "explicit123"

    def test_missing_id_exits_2(self):
        with pytest.raises(typer.Exit) as exc:
            require_list_id(None)
        assert exc.value.exit_code == 2


class TestHandleClickupErrors:
    def test_converts_clickup_error_to_exit_1(self):
        with pytest.raises(typer.Exit) as exc:
            with handle_clickup_errors():
                raise ClickUpError("boom")
        assert exc.value.exit_code == 1

    def test_passes_through_non_clickup_errors(self):
        with pytest.raises(ValueError, match="unrelated"):
            with handle_clickup_errors():
                raise ValueError("unrelated")

    def test_no_exception_is_fine(self):
        with handle_clickup_errors():
            pass


class TestGatherBounded:
    @pytest.mark.asyncio
    async def test_preserves_input_order(self):
        """Results must match the input order, not completion order."""

        async def delayed(value: int, delay: float) -> int:
            await asyncio.sleep(delay)
            return value

        # Intentionally make earlier tasks take longer
        coros = [delayed(i, 0.05 * (5 - i)) for i in range(5)]
        results = await gather_bounded(coros, limit=5)
        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_exceptions_returned_not_raised(self):
        """Exceptions should be returned in-place, not raised."""

        async def maybe_fail(i: int) -> int:
            if i == 2:
                raise ValueError("boom")
            return i

        results = await gather_bounded([maybe_fail(i) for i in range(4)], limit=4)
        assert results[0] == 0
        assert results[1] == 1
        assert isinstance(results[2], ValueError)
        assert results[3] == 3

    @pytest.mark.asyncio
    async def test_concurrency_bounded(self):
        """No more than ``limit`` coroutines should run simultaneously."""
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def track() -> None:
            nonlocal max_concurrent, current
            async with lock:
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
            await asyncio.sleep(0.02)
            async with lock:
                current -= 1

        await gather_bounded([track() for _ in range(10)], limit=3)
        assert max_concurrent <= 3

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Empty input should return an empty list."""
        results = await gather_bounded([], limit=5)
        assert results == []


class TestGetClient:
    @pytest.mark.asyncio
    async def test_no_credentials_exits_2(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        with pytest.raises(typer.Exit) as exc:
            await get_client()
        assert exc.value.exit_code == 2

    @pytest.mark.asyncio
    async def test_with_credentials_returns_provider(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test_token")
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        provider = await get_client()
        assert provider is not None
