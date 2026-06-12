"""Unit tests for clickup.cli.shared helpers."""

from __future__ import annotations

import asyncio
import json

import pytest
import typer

from clickup.cli.shared import gather_bounded, get_client, handle_clickup_errors, require_list_id, resolve_list_id
from clickup.core.exceptions import ClickUpError


class TestRequireListId:
    def test_returns_resolved_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        from clickup.core import Config

        Config().set("default_list_id", "L42")
        assert require_list_id(None) == "L42"

    def test_explicit_numeric_id_passes_through(self):
        assert require_list_id("12345") == "12345"

    def test_missing_id_exits_2(self):
        with pytest.raises(typer.Exit) as exc:
            require_list_id(None)
        assert exc.value.exit_code == 2


class TestResolveListIdValidation:
    """Tests for unknown-alias detection in resolve_list_id (item 2)."""

    def test_unknown_alias_clickup_provider_exits_2(self, monkeypatch, tmp_path):
        """Non-numeric, non-alias value with clickup provider should exit 2."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test_token")
        monkeypatch.delenv("CLICKUP_PROVIDER", raising=False)
        from clickup.core import Config

        config = Config()
        config.set("provider", "clickup")
        config.set("default_lists", {"inbox": "123", "work": "456"})

        with pytest.raises(typer.Exit) as exc:
            resolve_list_id("bogusalias")
        assert exc.value.exit_code == 2

    def test_known_alias_resolves(self, monkeypatch, tmp_path):
        """A configured alias should resolve to its numeric ID."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test_token")
        monkeypatch.delenv("CLICKUP_PROVIDER", raising=False)
        from clickup.core import Config

        config = Config()
        config.set("provider", "clickup")
        config.set("default_lists", {"inbox": "123"})

        assert resolve_list_id("inbox") == "123"

    def test_numeric_id_passes_through(self, monkeypatch, tmp_path):
        """A numeric ID should pass through without error."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.delenv("CLICKUP_PROVIDER", raising=False)
        from clickup.core import Config

        Config().set("provider", "clickup")
        assert resolve_list_id("999") == "999"

    def test_json_provider_passes_nonnumeric(self, monkeypatch, tmp_path):
        """json provider should pass non-numeric IDs through untouched."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setenv("CLICKUP_PROVIDER", "json")

        result = resolve_list_id("list_inbox")
        assert result == "list_inbox"

    def test_unknown_alias_error_lists_configured_aliases(self, monkeypatch, tmp_path, capsys):
        """The error message should include the configured alias names."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test_token")
        monkeypatch.delenv("CLICKUP_PROVIDER", raising=False)
        from clickup.cli.output import set_format
        from clickup.core import Config

        set_format("json")
        config = Config()
        config.set("provider", "clickup")
        config.set("default_lists", {"alpha": "1", "beta": "2"})

        with pytest.raises(typer.Exit):
            resolve_list_id("gamma")

        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert "alpha" in payload["error"]
        assert "beta" in payload["error"]
        assert "gamma" in payload["error"]

    def test_unknown_alias_no_aliases_configured(self, monkeypatch, tmp_path, capsys):
        """When no aliases are configured, error should say '(none)'."""
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test_token")
        monkeypatch.delenv("CLICKUP_PROVIDER", raising=False)
        from clickup.cli.output import set_format
        from clickup.core import Config

        set_format("json")
        Config().set("provider", "clickup")

        with pytest.raises(typer.Exit):
            resolve_list_id("bogus")

        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert "(none)" in payload["error"]


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
