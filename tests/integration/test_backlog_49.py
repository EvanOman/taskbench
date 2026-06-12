"""Tests for backlog-49 batch 1 features.

Covers:
- Item 1: batch task create
- Item 2: 401 message reword
- Item 3: zero-result hints
- Item 4: --name-only filter on task search
- Item 5: due-date format consistency
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app
from clickup.core.exceptions import ClickUpError
from clickup.core.models import StatusInfo, Task, User

from .conftest import make_mock_ctx

runner = CliRunner()


# ── helpers ──────────────────────────────────────────────────────────────


def _make_task(id: str, name: str, **overrides) -> Task:
    """Build a real Task model for tests that need model_dump."""
    kwargs = {"id": id, "name": name}
    kwargs.update(overrides)
    return Task(**kwargs)


# =============================================================================
# Item 1 — batch task create
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_batch_create_three_tasks_collection_envelope(mock_get_client):
    """3 names -> 3 tasks in order, collection envelope, flags applied to all."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task("t1", "Alpha", url="https://x/t1"),
        _make_task("t2", "Bravo", url="https://x/t2"),
        _make_task("t3", "Charlie", url="https://x/t3"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "Alpha",
            "Bravo",
            "Charlie",
            "--list-id",
            "L1",
            "--description",
            "shared desc",
            "--priority",
            "2",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3
    assert [t["name"] for t in data["data"]] == ["Alpha", "Bravo", "Charlie"]

    # Verify flags applied to every call
    for call in mock_client.create_task.await_args_list:
        assert call.kwargs["description"] == "shared desc"
        assert call.kwargs["priority"] == 2


@patch("clickup.cli.commands.task.get_client")
def test_single_create_unchanged_shape(mock_get_client):
    """Single name produces a singleton task object, NOT a collection envelope."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task("t1", "Solo", url="https://x/t1")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(app, ["task", "create", "Solo", "--list-id", "L1"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"
    assert data["name"] == "Solo"
    # No "data" / "count" keys — singleton shape
    assert "data" not in data
    assert "count" not in data


@patch("clickup.cli.commands.task.get_client")
def test_batch_create_partial_failure_exit_1(mock_get_client):
    """When some creates fail: successes rendered, failures warned, exit 1."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task("t1", "Good"),
        ClickUpError("rate limited"),
        _make_task("t3", "Also Good"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "Good", "Bad", "Also Good", "--list-id", "L1"],
    )

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    # Only the 2 successes appear in the envelope
    assert data["count"] == 2
    assert [t["name"] for t in data["data"]] == ["Good", "Also Good"]
    # Error on stderr
    assert "Failed to create task 'Bad'" in result.stderr


@patch("clickup.cli.commands.task.get_client")
def test_batch_create_brief(mock_get_client):
    """--brief works for batch creates."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = [
        _make_task("t1", "A", description="long text", url="https://x"),
        _make_task("t2", "B", description="long text 2", url="https://x"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "A", "B", "--list-id", "L1", "--brief"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    for t in data["data"]:
        assert "description" not in t


def test_batch_create_validates_each_name():
    """Each name is validated — empty names rejected."""
    result = runner.invoke(app, ["task", "create", "Good", "   ", "--list-id", "L1"])
    assert result.exit_code == 2
    assert "empty" in result.stderr.lower()


# =============================================================================
# Item 2 — 401 message wording
# =============================================================================


@pytest.mark.asyncio
async def test_401_resource_endpoint_leads_with_id_interpretation(mock_clickup_client):
    """Resource endpoint 401 now leads with 'the ID does not exist'."""
    from clickup.core.exceptions import ResourceAccessError

    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b'{"err": "Team not authorized"}'
    mock_response.json.return_value = {"err": "Team not authorized"}

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(ResourceAccessError) as exc:
        await mock_clickup_client._request("GET", "/task/doesnotexist123")
    msg = str(exc.value)
    # Message leads with the resource interpretation
    assert msg.startswith("ClickUp returned 401 for /task/doesnotexist123")
    assert "the ID does not exist" in msg
    assert "token itself is invalid" in msg


@pytest.mark.asyncio
async def test_401_auth_endpoint_leads_with_invalid_token(mock_clickup_client):
    """Auth endpoint (/user) 401 still leads with invalid token."""
    from clickup.core.exceptions import AuthenticationError

    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.content = b'{"err": "Unauthorized"}'
    mock_response.json.return_value = {"err": "Unauthorized"}

    mock_clickup_client.client.request.return_value = mock_response

    with pytest.raises(AuthenticationError) as exc:
        await mock_clickup_client._request("GET", "/user")
    msg = str(exc.value)
    assert "invalid API token" in msg


# =============================================================================
# Item 3 — zero-result hints
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_zero_result_hint_filtered_empty_table_mode(mock_get_client):
    """Filtered-empty emits info message with pre-filter count in table mode.

    Uses --open-only because it's a client-side filter in task list,
    so pre_filter_count reflects the full API result. status filters go to
    the API directly, so the pre-filter count wouldn't show a difference.
    """
    mock_client = AsyncMock()
    # List has 5 tasks, all closed — open-only will filter them all out
    tasks = [_make_task(f"t{i}", f"Task {i}", status=StatusInfo(status="complete", type="closed")) for i in range(5)]
    mock_client.get_tasks.return_value = tasks
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "list", "--list-id", "L1", "--open-only"],
    )

    assert result.exit_code == 0
    # The hint goes to stdout in table mode (via render_message info level -> Rich console on stdout)
    combined = result.stdout + result.stderr
    assert "0 tasks matched the active filters" in combined
    assert "5 tasks total" in combined


@patch("clickup.cli.commands.task.get_client")
def test_zero_result_hint_json_mode_suppressed(mock_get_client):
    """In JSON mode, info-level hint is suppressed; only envelope on stdout."""
    mock_client = AsyncMock()
    tasks = [_make_task(f"t{i}", f"Task {i}", status=StatusInfo(status="complete", type="closed")) for i in range(3)]
    mock_client.get_tasks.return_value = tasks
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "list", "--list-id", "L1", "--open-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == {"data": [], "count": 0}
    # info-level message suppressed in JSON mode
    assert "0 tasks matched" not in result.stdout


@patch("clickup.cli.commands.task.get_client")
def test_zero_result_no_hint_when_unfiltered(mock_get_client):
    """Unfiltered empty list emits 'No tasks found' — no hint about filters."""
    mock_client = AsyncMock()
    mock_client.get_tasks.return_value = []
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "list", "--list-id", "L1"],
    )

    assert result.exit_code == 0
    combined = result.stdout + result.stderr
    assert "0 tasks matched the active filters" not in combined


@patch("clickup.cli.commands.task.get_client")
def test_zero_result_hint_task_search_with_filters(mock_get_client):
    """task search emits zero-result hint when filters are active."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task("t1", "Alpha", status=StatusInfo(status="open")),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "search", "--query", "alpha", "--status", "closed", "--workspace-id", "W1"],
    )

    assert result.exit_code == 0
    combined = result.stdout + result.stderr
    assert "0 tasks matched the active filters" in combined


@patch("clickup.cli.commands.task.get_client")
def test_zero_result_hint_task_mine_with_filters(mock_get_client):
    """task mine emits zero-result hint when filters are active."""
    mock_client = AsyncMock()
    mock_client.get_user.return_value = User(id=42, username="evan", email="e@x.com")
    mock_client.search_tasks.return_value = [
        _make_task("t1", "My Task", status=StatusInfo(status="open")),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["--format", "table", "task", "mine", "--workspace-id", "W1", "--open-only"],
    )

    # With open-only, 1 task matches (it's open), so no hint here.
    # Let's test with a status that filters everything out.
    mock_client.search_tasks.return_value = [
        _make_task("t1", "My Task", status=StatusInfo(status="open")),
    ]
    result = runner.invoke(
        app,
        ["--format", "table", "task", "mine", "--workspace-id", "W1", "--status", "nonexistent"],
    )

    assert result.exit_code == 0
    combined = result.stdout + result.stderr
    assert "0 tasks matched the active filters" in combined


# =============================================================================
# Item 4 — task search --name-only
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_name_only_filters_by_task_name(mock_get_client):
    """--name-only keeps only tasks whose name contains the query (case-insensitive)."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task("t1", "Deploy API"),
        _make_task("t2", "Write API docs"),
        _make_task("t3", "Fix login bug"),  # 'api' only in description/comments
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "api", "--workspace-id", "W1", "--name-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2
    names = [t["name"] for t in data["data"]]
    assert "Deploy API" in names
    assert "Write API docs" in names
    assert "Fix login bug" not in names


@patch("clickup.cli.commands.task.get_client")
def test_name_only_case_insensitive(mock_get_client):
    """--name-only matching is case-insensitive."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [
        _make_task("t1", "URGENT Bug Fix"),
        _make_task("t2", "urgent refactor"),
        _make_task("t3", "Normal task"),
    ]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "urgent", "--workspace-id", "W1", "--name-only"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 2


@patch("clickup.cli.commands.task.get_client")
def test_name_only_with_limit(mock_get_client):
    """--name-only + --limit: count reflects the filtered (then truncated) set."""
    mock_client = AsyncMock()
    mock_client.search_tasks.return_value = [_make_task(f"t{i}", f"Matching {i}") for i in range(10)]
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "search", "--query", "Matching", "--workspace-id", "W1", "--name-only", "--limit", "3"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 3


# =============================================================================
# Item 5 — due-date format consistency
# =============================================================================


@patch("clickup.cli.commands.task.get_client")
def test_create_due_date_accepts_yyyy_mm_dd(mock_get_client):
    """task create --due-date 2026-07-01 sends epoch ms to the provider."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "2026-07-01"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    due_val = call_kwargs["due_date"]
    # Should be epoch-ms string for 2026-07-01 00:00:00 UTC
    assert due_val == str(1782864000000)


@patch("clickup.cli.commands.task.get_client")
def test_create_due_date_accepts_relative(mock_get_client):
    """task create --due-date 7d sends an epoch-ms in the recent past."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "7d"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    due_val = int(call_kwargs["due_date"])
    # Should be a valid epoch-ms (roughly now - 7 days)
    assert due_val > 0


@patch("clickup.cli.commands.task.get_client")
def test_update_due_date_accepts_yyyy_mm_dd(mock_get_client):
    """task update --due-date 2026-07-01 sends epoch ms to the provider."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "2026-07-01"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    due_val = call_kwargs["due_date"]
    assert due_val == str(1782864000000)


@patch("clickup.cli.commands.task.get_client")
def test_update_due_date_accepts_relative(mock_get_client):
    """task update --due-date 7d sends epoch ms."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "7d"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    due_val = int(call_kwargs["due_date"])
    assert due_val > 0


@patch("clickup.cli.commands.task.get_client")
def test_update_due_date_accepts_epoch_ms(mock_get_client):
    """task update --due-date <epoch-ms> passes through unchanged."""
    mock_client = AsyncMock()
    mock_client.update_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "update", "t1", "--due-date", "1782691200000"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.update_task.call_args.kwargs
    assert call_kwargs["due_date"] == "1782691200000"


@patch("clickup.cli.commands.task.get_client")
def test_create_due_date_accepts_epoch_ms(mock_get_client):
    """task create --due-date <epoch-ms> passes through unchanged."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = _make_task("t1", "X")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        ["task", "create", "X", "--list-id", "L1", "--due-date", "1782691200000"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.create_task.call_args.kwargs
    assert call_kwargs["due_date"] == "1782691200000"
