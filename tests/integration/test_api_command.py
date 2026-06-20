"""Tests for the raw API escape hatch."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from taskbench.cli.main import app
from taskbench.core.exceptions import ClickUpError

runner = CliRunner()


def _ctx(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


@patch("taskbench.cli.commands.api.get_client")
def test_api_request_get_json(mock_get_client):
    mock_client = AsyncMock()
    mock_client.raw_request.return_value = {"id": "task123", "name": "Task"}
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        ["api", "GET", "/task/task123", "--param", "include_subtasks=true"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "task123"
    mock_client.raw_request.assert_awaited_once_with(
        "GET",
        "/task/task123",
        params={"include_subtasks": "true"},
    )


@patch("taskbench.cli.commands.api.get_client")
def test_api_request_repeated_params_become_list(mock_get_client):
    mock_client = AsyncMock()
    mock_client.raw_request.return_value = {"ok": True}
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        ["api", "GET", "/list/L1/task", "--param", "statuses[]=open", "--param", "statuses[]=review"],
    )

    assert result.exit_code == 0
    mock_client.raw_request.assert_awaited_once_with(
        "GET",
        "/list/L1/task",
        params={"statuses[]": ["open", "review"]},
    )


@patch("taskbench.cli.commands.api.get_client")
def test_api_request_post_with_json_body(mock_get_client):
    mock_client = AsyncMock()
    mock_client.raw_request.return_value = {"ok": True}
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(
        app,
        ["api", "POST", "/task/task123/comment", "--data", '{"comment_text":"hello"}'],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    mock_client.raw_request.assert_awaited_once_with(
        "POST",
        "/task/task123/comment",
        json={"comment_text": "hello"},
    )


def test_api_request_rejects_invalid_method():
    result = runner.invoke(app, ["api", "TRACE", "/task/task123"])
    assert result.exit_code == 2
    assert "unsupported method" in result.stderr


def test_api_request_rejects_invalid_json_data():
    result = runner.invoke(app, ["api", "POST", "/task/task123", "--data", "{bad"])
    assert result.exit_code == 2
    assert "--data must be valid JSON" in result.stderr


def test_api_request_rejects_invalid_param():
    result = runner.invoke(app, ["api", "GET", "/task/task123", "--param", "bad"])
    assert result.exit_code == 2
    assert "key=value" in result.stderr


def test_api_request_rejects_empty_param_key():
    result = runner.invoke(app, ["api", "GET", "/task/task123", "--param", "=bad"])
    assert result.exit_code == 2
    assert "key cannot be empty" in result.stderr


@patch("taskbench.cli.commands.api.get_client")
def test_api_request_handles_clickup_error(mock_get_client):
    mock_client = AsyncMock()
    mock_client.raw_request.side_effect = ClickUpError("boom")
    mock_get_client.return_value = _ctx(mock_client)

    result = runner.invoke(app, ["api", "GET", "/task/task123"])

    assert result.exit_code == 1
    assert "ClickUp API Error: boom" in result.stderr


def test_api_request_without_credentials_errors(monkeypatch):
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
    with monkeypatch.context() as m:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            m.setenv("CLICKUP_CONFIG_PATH", f"{tmpdir}/config.json")
            result = runner.invoke(app, ["api", "GET", "/task/task123"])

    assert result.exit_code == 2
    assert "No ClickUp API token configured" in result.stderr
