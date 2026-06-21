# Agent Instructions

## Project goal in one line

A task-management CLI that an AI coding agent can drive end-to-end through stdin/stdout — no MCP, no UI, no skills required for basic use. ClickUp is the default backend, but the CLI is backend-pluggable (see "Backends"). Linear MCP's "modify if passed" semantics for writes.

## Docs map (start here if you're new)

| You want to... | Read |
|---|---|
| Understand the system in 2 minutes | `docs/architecture.md` |
| Run the CLI against a backend (incl. zero-infra local) | `docs/backends.md` |
| Add a new backend adapter | `docs/writing-an-adapter.md` |
| Implement a backend in another language | `spec/openapi.yaml` + `spec/README.md` |
| Know the behavioral rules before changing code | this file, "Architecture decisions" |

## Technology stack (required)

| Tool | Purpose |
|---|---|
| Python 3.12+ | Runtime |
| uv | Package manager, virtual envs |
| Typer | CLI framework |
| httpx | HTTP client (async) |
| pydantic | Data models + validation |
| rich | Terminal output (sparingly — agents are the primary consumer) |
| pytest | Tests |
| ruff | Lint + format |
| ty | Type checking |

**Do not introduce JavaScript/Node tooling.** Do not add MCP server code (lived briefly, removed in commit `81c42c9`).

## Distribution

The CLI ships as a single Python package. Real-world install paths, in priority order:

1. **One-shot via uvx** (the agent default):
   ```bash
   uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench ...
   ```
2. **Persistent install** (faster, daily use):
   ```bash
   uv tool install git+https://github.com/EvanOman/clickup-tools.git
   taskbench ...      # full name
   tb ...             # short alias (same binary, registered in pyproject.toml)
   ```
3. **Local dev:** `uv sync && uv run taskbench ...`

`pyproject.toml` registers both `taskbench` and `tb` entry points; treat them as equivalent.

### Local dev caveat

**Do not use `uvx --from .` or `uvx --from /path/to/clickup-tools` for local development.** uvx builds a wheel and caches it by package name+version; subsequent invocations at the same version silently serve the stale wheel, so source edits have no effect until the version is bumped or the cache is pruned. This bit us at v0.2.0 (spinner removal was invisible until v0.3.0).

The fix is simple: always use `uv run taskbench ...` (or `just cli ...`) from the project directory. `uv sync` installs the project as an editable package (via `.pth` file), so every invocation reads live source — no build, no cache, no surprises. Reserve `uvx` for end-users and agents consuming a pinned release from git.

## Project layout

For the *current* file tree, run:

```
ls taskbench/ taskbench/cli/ taskbench/core/ tests/ docs/ spec/
```

What each top-level subpackage means (this is what doesn't change; file
names occasionally do):

- **`taskbench/core/`** — the backend layer. Owns the `TaskProvider`
  protocol that every backend implements, the pydantic models that flow
  through it (`models.py`), the configuration loader (`config.py`),
  built-in adapters for ClickUp and a file-backed JSON store, exception
  taxonomy, and the `get_provider()` factory that loads external adapters
  via `importlib.metadata` entry points (group `taskbench.providers`).
- **`taskbench/cli/`** — the user-facing Typer app.
  - `main.py`: root Typer callback, `--format` flag plumbing, top-level
    `status`/`version` commands, error envelope wiring.
  - `output.py`: **every** user-visible render goes through here — JSON
    or table, agents-first. See decision 1 below.
  - `shared.py`: cross-command helpers (`get_client`, `usage_error`,
    `resolve_*`, the batch-results partitioner, etc.).
  - `task_filters.py`: pure filter/sort/validation logic for task
    commands.
  - `utils.py`: small async runner.
  - `commands/`: one file per feature group (`task.py`, `list.py`,
    `bulk.py`, `discover.py`, `config.py`, etc.). Each registers a Typer
    sub-app on the root.
- **`docs/`** — architecture, backends-as-product, adapter-author guide,
  written for humans.
- **`spec/`** — OpenAPI projection of `TaskProvider` plus design notes,
  for backends implemented in other languages.
- **`tests/unit/`** — fast, mocked.
- **`tests/integration/`** — drives the CLI through `CliRunner`. Most
  mock the provider; `test_mock_provider.py` and
  `test_e2e_json_scenario.py` exercise the file-backed `JsonProvider`
  end-to-end (see "Decision 9" / the scenario-test rationale below).
- **`tests/live/`** — `@pytest.mark.live`, hits the real ClickUp API.
  Opt-in only.
- **`.claude/skills/cli-agent-eval/`** — the 18-task agent eval (see
  "Eval skill").
- **`evals/`** — historical per-commit eval results (`<sha>-rN.json`).

## Backends (providers)

The CLI is backend-pluggable via the `TaskProvider` protocol
(`taskbench/core/providers.py`). Select with `TASKBENCH_PROVIDER` (legacy `CLICKUP_PROVIDER` still works with a deprecation warning):

- `clickup` (default) — the real SaaS; needs `CLICKUP_API_KEY`
- `json` / `local` / `mock` — file-backed, **zero setup**; use this for development and evals

External adapters are discovered via `entry_points(group="taskbench.providers")`.
See `docs/writing-an-adapter.md` for how to write one.

Spin-up commands, env vars, and verification steps per backend: **`docs/backends.md`**.
Deployment code never lives in this repo — adapters only.

Two contract surfaces, one source of truth: the Python protocol is canonical;
`spec/openapi.yaml` is its HTTP projection for non-Python implementers. If a
PR changes `TaskProvider` or the models, it must update the spec too.

## Architecture decisions (load-bearing — don't undo without reason)

### 1. Output goes through `taskbench/cli/output.py`

Every user-visible output is rendered via functions in `taskbench/cli/output.py`:
`render_user`, `render_team(s)`, `render_space(s)`, `render_list(s)`, `render_task(s)`, `render_comments`, `render_kv`, `render_message`. They read the global format setting via `get_format()` and emit either a Rich table or structured JSON.

Direct `console.print` of structured data is a regression — route it through a renderer instead. All commands now route through `output.py` renderers.

JSON shape:
- Collections: `{"data": [...], "count": N}` — collections MAY carry `"truncated": true` when `--limit` clipped the result set.
- Singletons: `model.model_dump(mode="json")` (gives ISO 8601 timestamps via pydantic)

### 2. `--format` is a GLOBAL flag, not per-command

Wired on the root Typer callback in `main.py`. **JSON is the default** — agents are first-class consumers, so the unflagged path emits structured data. Pass `taskbench --format table <subcommand> ...` for human-readable output. Since v0.4.4 the flag is also **accepted after the subcommand**: `main()` hoists a trailing `--format <value>` to the front before parsing (`_hoist_global_format`), because agent evals showed 7 of 18 fresh agents instinctively append it. The hoist is skipped for `export-tasks`, whose own `--format` alias (output FILE format, csv/json — deprecated alias of `--output-format`) must keep its local meaning; `task export` uses only `--output-format`. Don't declare `--format` on any new subcommand — the hoist plus root callback already covers it.

### 3. Modify-if-passed update semantics

`task update` (and any future update command) checks `if value is not None` — never truthy. This lets agents pass `--description ""` to clear a field. Only fields explicitly passed are sent to the API; the rest stay as ClickUp had them.

### 4. Destructive ops never prompt; require `--force`/`--yes`

The CLI is agent-first. Any operation that would destroy or mutate state at scale (`task delete`, `config reset`, `config clean`, `bulk import-tasks`, `bulk bulk-update`) requires an explicit `--force/-f` (alias `--yes/-y`) flag. Without the flag, the command exits 2 with a clear "Refusing to ..." message on stderr — it does not fall through to a `typer.confirm` prompt.

The interactive flows that intentionally remain interactive (`taskbench setup run` and `taskbench template create --interactive`) are bootstrap / authoring tools meant for humans. `setup run` accepts `--token / --team-id / --space-id / --list-id / --non-interactive` for agent use; `template create` is gated behind `--interactive`. Neither is part of the destructive-op contract.

Reasons:
- Interactive prompts wedge agents that drive the CLI over stdio. They also break parallel/batch invocations (the prompt deadlocks while the harness waits for output).
- A required flag is self-documenting in shell history and unambiguous in scripts.
- `--yes` is the conventional alias users reach for first; `--force` is the existing flag. Both must be accepted everywhere.

If you add a new command that mutates state irreversibly, follow the same pattern: declare the flag with all four spellings on a single Option, refuse to proceed without it, and exit 2 (not 1 — exit 2 is a usage error so it's distinct from API failures which exit 1).

### 4a. Errors go to stderr

All error and refusal messages route through `render_error()` in `taskbench/cli/output.py`, which writes to **stderr** via `typer.echo(..., err=True)`. In `--format json` mode, errors emit `{"error": ...}` to stderr — never to stdout. This keeps stdout clean for data pipelines: a caller can do `tb --format json task list ... > data.json` and any failures land on stderr where they belong.

Convention: `render_error(msg)` then `raise typer.Exit(code)` — `code=1` for runtime/API errors, `code=2` for usage errors.

### 5. No spinner, no Progress widgets

The original codebase had no-op shims for `Progress`, `SpinnerColumn`, `TextColumn`, `BarColumn`, `TaskProgressColumn` in `taskbench/cli/utils.py`. Those spinner shims have since been removed entirely; nothing imports `rich.progress`. The rationale remains: spinner frames on stdout corrupt `--format json` pipelines and agents don't benefit from animation.

If you need user feedback for a slow operation, write a one-line message to **stderr**, not stdout.

### 6. Rich markup is dangerous on user data

Rich interprets `[bold]`, `[red]`, etc. inside printed strings — and silently strips brackets in unrecognized markup. Task names like `[bug] foo` get destroyed without `rich.markup.escape()`. The renderers in `output.py` escape; new rendering code MUST do the same.

### 7. Config priority

`get_api_token()` priority: `CLICKUP_API_KEY` env var (or `CLICKUP_API_TOKEN`) > persisted config (`~/.config/taskbench/config.json`).
`.env` files are loaded at module import time from:
1. `~/.config/taskbench/.env` (user-global; falls back to `~/.config/clickup-toolkit/.env` with deprecation warning)
2. `.env` in current working directory (project-local; uses `find_dotenv` walk)

Config path can be overridden with `TASKBENCH_CONFIG_PATH` (legacy `CLICKUP_CONFIG_PATH` still works with a deprecation warning).

For users invoking via uvx from outside the project root, recommend the user-global `.env`.

### 8. Test isolation

`tests/conftest.py` has an autouse fixture that:
- Strips `TASKBENCH_*` and `CLICKUP_*` env vars
- Redirects `Config._get_default_config_path` to a per-test tmpdir

This was added because tests instantiating bare `Config()` were silently writing to the real user config. Don't undo it. Tests marked `@pytest.mark.live` opt out so they can hit the real API.

The setup wizard's interactive prompts (in `taskbench/cli/commands/setup.py`) can still pollute the real config when human-tested. Treat that as a known caveat.

## Parked features

Branch `parked/incomplete-features` holds:
- OAuth flow + auth command
- Webhook server + webhook command
- NLP task parsing module + nlp command
- Dark-mode theme spec

These were 100% incomplete and outside the agent-CLI core. They're checked in on the parked branch so they're not lost. Don't merge them back without explicit user direction; if revisited, redo the design (likely simpler).

## Eval skill (regression checking)

`.claude/skills/cli-agent-eval/SKILL.md` is a fixed 12-task swarm that exercises agent-usability paths against a live ClickUp account. Run it after non-trivial CLI changes:

> "Run the cli-agent-eval skill"

Each task spawns an Opus sub-agent with no source-reading allowed; it tests via `uvx --python 3.13 --from <project> taskbench ...`. Results saved to `evals/<short-sha>.json` so deltas can be tracked.

Per-task metrics captured:
- `verdict` ∈ {pass, partial, fail}
- `command_count`
- `elapsed_seconds`
- `top_friction` (free text)

The baseline (pre-refactor) had 16 friction items; post-refactor passes 11/12. The remaining gaps are tracked in the GitHub issue tracker (see "Next batch" issue).

## Development commands

All commands run from the project root.

- `uv sync` — install deps
- `just fc` — format + lint-fix + lint + type + test (run before every commit)
- `just check` — same without auto-fix (for CI parity)
- `just test-live` — run `tests/live/` against the real API (needs `CLICKUP_API_KEY`)
- `just cli ...` — invoke the CLI under uv

## Critical conventions

- No `cd` in scripts; use absolute paths only when truly required
- No absolute paths in code (config dir is computed via `Path.home()`)
- Don't reintroduce mypy — replaced by ty
- Don't push to `master` without `just fc` passing AND the CI green
- New commands: register them in `taskbench/cli/main.py` with `rich_help_panel` so they appear in the right `--help` group ("Get started", "Task workflow", "Workspace navigation", "Other")

## CLAUDE.md

`CLAUDE.md` just points here. Keep it that way — single source of truth.

## Decision log

Non-obvious choices and why they were made, for future contributors.

**Why no PyPI yet** — The package isn't stable enough for a public API contract; tight iteration without semver pressure is the priority. Distribution via `uvx --from git+...` gives the same end-user UX without committing to PyPI's release cadence and yank limitations. Revisit when the agent-CLI surface area stabilizes.

**Why hatchling, not uv_build** — `pystd` recommends `uv_build` for new projects, but this project predates that recommendation and chose hatchling. Both work for `uv build` and `uvx --from <path>`. Switching incurs config churn for no observable benefit; keep hatchling.

**Why the test-isolation fixture patches both `_get_default_config_path` and `_get_config_path`** — Discovered (commit `9966d6c`) that several legacy tests instantiate bare `Config()` and call `.set(...)`, which writes to the config file in production. Stripping `CLICKUP_*` env vars wasn't enough — the persisted file leaked test data into real user config. Patching both path-resolution methods routes those writes to a per-test tmp file. `@pytest.mark.live` tests opt out so they hit the real env.

**Why a no-spinner shim instead of editing every call site** — Originally, `Progress`, `SpinnerColumn`, `TextColumn`, `BarColumn`, `TaskProgressColumn` were stubbed to no-ops in `taskbench/cli/utils.py`. Existing `with Progress(...) as p: p.add_task(...)` blocks compiled and ran silently. This kept the change to one PR with low diff and zero risk of missing a call site. The shims have since been removed entirely (no call sites remain); nothing imports `rich.progress`.

**Why `tb` alongside `taskbench`** — `taskbench` is the canonical name (self-documenting in shell history); `tb` is the daily-driver short alias. Both registered as entry points in `pyproject.toml`. Adding `tb` was free.

**Why the rename from clickup-toolkit to taskbench** — The CLI outgrew ClickUp: the `TaskProvider` protocol, the JSON local adapter, and entry-point plugin discovery mean any backend can be swapped in. The old name implied ClickUp-only. The rename also drops the `cup` binary (replaced by `tb`), moves the config dir to `~/.config/taskbench/`, and bumps to 1.0.0. Legacy env vars (`CLICKUP_PROVIDER`, `CLICKUP_CONFIG_PATH`) emit a one-time deprecation warning and continue to work.

**uvx caching for local dev** — See "Distribution" section above for the local-dev mitigation.

## Roadmap

The active backlog lives in the GitHub issue tracker, not this file.
`gh issue list --state open` is the source of truth; the factory-readiness
assessment lives at [#67](https://github.com/EvanOman/taskbench/issues/67)
and tracks the multi-iteration items (P1b deterministic eval subset, P2
contract forward-test, P4 self-deprecating feedback loop). Anything not
on the issue tracker is not committed work — please file before
starting.

For the recent history of *what just landed*: `git log --oneline -20`
or `evals/` (per-commit eval results encode the surface changes agents
actually noticed).
