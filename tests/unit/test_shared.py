"""Unit tests for clickup.cli.shared helpers."""

from __future__ import annotations

import pytest
import typer

from clickup.cli.shared import get_client, handle_clickup_errors, require_list_id
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
