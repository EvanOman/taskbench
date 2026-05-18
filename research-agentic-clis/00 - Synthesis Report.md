---
tags:
  - ai-generated
  - agentic-cli
  - clickup-tools
---

# Agentic CLI Synthesis for clickup-tools

## Core Takeaway

`clickup-tools` should stop treating the current GitHub issues as an implementation queue and instead define a small agent-first contract. The winning pattern across `gh`, Linear, Taskwarrior, GitLab, Jira, and cloud CLIs is not "many convenience flags"; it is a predictable local API: stable resource nouns, one broad sparse-update surface, explicit action commands for non-field operations, structured JSON for every success and failure, and no hidden workflow assumptions.

For this project, the primary user is an LLM agent operating a short-horizon personal ClickUp queue. That means correctness, inspectability, and recoverability matter more than terminal terseness.

## Recommended Shape

Keep the command model small:

```text
cup task list
cup task view TASK
cup task create ...
cup task update TASK ...
cup task comment TASK ...
cup task delete TASK --force
cup task statuses --list-id LIST
cup api ...
```

Use `task update` as the broad Linear-like sparse patch surface:

```bash
cup task update TASK_ID \
  --name "Tighten JSON contract" \
  --status "in progress" \
  --priority 2 \
  --due-date 2026-05-20
```

Keep separate commands only when the backend operation is conceptually separate: comments, delete, status discovery, custom-field writes, dependencies, raw API calls.

## JSON Contract

In machine mode, stdout should contain exactly one JSON value and no prose.

Recommended envelopes:

```json
{"data": {...}}
```

```json
{"data": [...], "count": 3, "has_more": false, "next_page": null}
```

```json
{
  "error": {
    "type": "usage",
    "title": "Invalid argument",
    "detail": "--sort direction must be 'asc' or 'desc'.",
    "exit_code": 2,
    "retryable": false
  }
}
```

Every mutation should return the resulting resource or a typed operation result. Never return `"Created task: ..."` in JSON mode.

## Product Boundaries

Do not add workflow semantics unless ClickUp natively stores them or the user explicitly configures the storage. The closed blocker issue is the example: task dependencies are native, external PR blockers are not.

Workspace-specific reality belongs in config:

```bash
cup config set default_list_id 123
cup config set list_alias.personal 456
cup config set status_alias.started "in progress"
cup config set field_alias.external_url abc123
```

Prompt conventions should carry soft behavior like "write action-oriented personal task titles" or "do not move tasks between lists unless asked."

## Issue Triage

- `#22` should become the umbrella "agent contract" issue, but split into smaller pieces. First implementation slice: JSON output for task mutations.
- `#21` should stay open as query ergonomics, but only API-grounded filters should survive: date ranges, multi-status, multi-list/default aliases, open/closed handling.
- `#24` should be closed or rewritten as partially stale. Direction-aware sort and default list support appear already implemented; the remaining `--all-lists` idea belongs with `#21`.
- New issue worth creating: `Define agent JSON contract for all commands`.
- New issue worth creating: `Add raw cup api escape hatch`.

## First Milestone

1. Define JSON success/error envelopes.
2. Make `task create`, `task update`, `task status/start/done/park`, and `task delete` honor the JSON contract.
3. Add tests that assert stdout is valid JSON in `--format json` mode.
4. Add `task statuses` or `list statuses` discovery before adding more status conveniences.
5. Add `cup api` before adding many specialized ClickUp feature flags.

