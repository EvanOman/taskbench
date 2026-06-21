"""End-to-end scenario against the JSON provider.

The other tests in this directory exercise individual commands; this one
walks an entire realistic agent workflow as one connected sequence.
Every step asserts both exit code and JSON shape, so any breakage in the
CLI wiring — provider plumbing, output contract, batch semantics —
surfaces as a single loud, narratable failure.

Issue #67 P1a: 'an AI with no human in the loop should be able to tell
you if a PR breaks functionality'. This file is that signal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from taskbench.cli.main import app

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated config + a fresh JSON store, then point the CLI at them."""
    config_path = tmp_path / "config.json"
    store_path = tmp_path / "store.json"
    monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(config_path))
    # Bootstrap the store via the real CLI command — the same path an agent uses.
    init = runner.invoke(app, ["mock", "init", "--path", str(store_path)])
    assert init.exit_code == 0, init.stdout
    monkeypatch.setenv("CLICKUP_JSON_STORE_PATH", str(store_path))
    return store_path


def _ok(result, *, code: int = 0) -> dict:
    """Assert exit code, parse stdout as JSON, return the object."""
    assert result.exit_code == code, f"exit={result.exit_code} stdout={result.stdout!r} stderr={result.stderr!r}"
    return json.loads(result.stdout)


def test_full_agent_workflow_against_json_provider(env: Path) -> None:
    """One linear story: orient → create → update → comment → search → close → delete.

    The shape of every JSON envelope on the happy path is pinned here. If
    any single command starts emitting prose, an extra wrapper, the wrong
    exit code, or the wrong key names, this test fails clearly.
    """

    # ── orient ────────────────────────────────────────────────────────────
    status = _ok(runner.invoke(app, ["status"]))
    assert status["user_name"], "status must expose authenticated user"
    assert status["user_email"]

    teams = _ok(runner.invoke(app, ["workspace", "list"]))
    assert teams["count"] >= 1
    assert teams["data"][0]["name"] == "Mock Workspace"
    team_id = teams["data"][0]["id"]

    hierarchy = _ok(runner.invoke(app, ["discover", "hierarchy", "--team-id", team_id]))
    spaces = hierarchy["workspaces"][0]["spaces"]
    assert spaces, "seed store must include at least one space"
    # discover hierarchy returns list IDs nested under spaces.folders[].lists or spaces.folderless_lists
    list_ids: list[str] = []
    for sp in spaces:
        for f in sp.get("folders", []):
            list_ids.extend(lst["id"] for lst in f.get("lists", []))
        list_ids.extend(lst["id"] for lst in sp.get("folderless_lists", []))
    assert list_ids, "seed store must expose at least one list via the hierarchy"
    list_id = list_ids[0]

    # list stats is the 'where's the action?' shortcut.
    stats = _ok(runner.invoke(app, ["list", "stats"]))
    assert stats["count"] >= 1
    assert {"name", "id", "task_count", "open_count", "last_updated"} <= set(stats["data"][0])

    # ── batch create (variadic) ───────────────────────────────────────────
    batch = _ok(
        runner.invoke(
            app,
            [
                "task",
                "create",
                "scenario-a",
                "scenario-b",
                "scenario-c",
                "--list-id",
                list_id,
            ],
        )
    )
    assert batch["count"] == 3
    assert [t["name"] for t in batch["data"]] == ["scenario-a", "scenario-b", "scenario-c"]
    ids = [t["id"] for t in batch["data"]]

    # ── modify-if-passed semantics ────────────────────────────────────────
    # The CLI flattens PriorityInfo to {priority: int, priority_label: str} —
    # the agent-friendly shape, not the wire shape. Pinning that here so any
    # accidental shape regression is loud.
    updated = _ok(runner.invoke(app, ["task", "update", ids[0], "--priority", "2"]))
    assert updated["priority"] == 2, updated
    assert updated["priority_label"] == "high"
    assert updated["name"] == "scenario-a", "name must be untouched"
    refetched = _ok(runner.invoke(app, ["task", "get", ids[0]]))
    assert refetched["priority"] == 2
    assert refetched["priority_label"] == "high"
    assert refetched["name"] == "scenario-a"

    # ── comment round-trip ────────────────────────────────────────────────
    runner.invoke(app, ["task", "comments", "add", ids[1], "scenario flow check"])
    listed = _ok(runner.invoke(app, ["task", "comments", "list", ids[1]]))
    assert listed["count"] == 1
    assert listed["data"][0]["comment_text"] == "scenario flow check"

    # ── search ────────────────────────────────────────────────────────────
    search_results = _ok(
        runner.invoke(
            app,
            ["task", "search", "--query", "scenario", "--team-id", team_id, "--brief"],
        )
    )
    found_names = {t["name"] for t in search_results["data"]}
    assert {"scenario-a", "scenario-b", "scenario-c"} <= found_names

    # ── close all three (variadic done) ───────────────────────────────────
    closed = _ok(runner.invoke(app, ["task", "done", *ids]))
    assert closed["count"] == 3
    for t in closed["data"]:
        assert t["status"]["status"] == "complete"

    # ── delete all three (variadic delete) ────────────────────────────────
    deleted = _ok(runner.invoke(app, ["task", "delete", *ids, "--force"]))
    assert deleted["count"] == 3
    assert all(item["deleted"] for item in deleted["data"])

    # Final sanity: the deleted IDs are gone.
    after = _ok(runner.invoke(app, ["task", "list", "--list-id", list_id]))
    surviving_ids = {t["id"] for t in after["data"]}
    assert not surviving_ids.intersection(ids), "deleted tasks must not survive in the list"
