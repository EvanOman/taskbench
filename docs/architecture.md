# Architecture

One diagram, then where to find everything.

```
                  ┌────────────────────────────────────────────┐
                  │ clickup/cli/                               │
  agent ──stdio──▶│   main.py        Typer root, global --format,
                  │                  exit codes, JSON error envelope
                  │   commands/*.py  per-feature subcommands    │
                  │   output.py      ALL rendering (table/JSON) │
                  └───────────────┬────────────────────────────┘
                                  │ TaskProvider protocol
                                  │ (clickup/core/providers.py)
                  ┌───────────────┴────────────────────────────┐
                  │ adapters (clickup/core/)                   │
                  │   client.py           ClickUp SaaS (httpx) │
                  │   json_provider.py    local JSON file      │
                  │   planka_provider.py  Planka via plankapy  │
                  └───────────────┬────────────────────────────┘
                                  │ pydantic models (models.py)
                                  ▼
                          backend of choice
```

## The contract stack

1. **`TaskProvider`** (`clickup/core/providers.py`) — the Python protocol all
   adapters implement. ~25 async methods over the hierarchy
   workspace → space → folder → list → task → comment. **Source of truth.**
2. **`spec/openapi.yaml`** — the HTTP projection of that protocol, for
   non-Python backend implementers. Derived; update it whenever the protocol
   changes. Design rationale in `spec/README.md`.
3. **Models** (`clickup/core/models.py`) — pydantic, ClickUp-shaped wire
   format (epoch-ms-string timestamps, string IDs, `extra="allow"`
   everywhere). Adapters translate their backend's shapes into these.

## Key flows

**Provider selection** — `get_provider()` reads `CLICKUP_PROVIDER` env var,
then the `provider` config key, defaulting to `clickup`. See
`docs/backends.md` for running each one.

**Output** — every command renders through `clickup/cli/output.py`. JSON is
the *default* format (agents are the primary consumer); `--format table` is
the human opt-in. Collections emit `{"data": [...], "count": N}`.

**Errors** — exceptions (`clickup/core/exceptions.py`) are caught in
`main.py` and rendered by `render_error()` to **stderr** (as `{"error": ...}`
in JSON mode), keeping stdout clean for pipelines. Exit codes: `0` success,
`1` runtime/API error, `2` usage error (including refused destructive ops).

**Config** — `~/.config/clickup-toolkit/config.json` plus `.env` loading;
env vars always win. `default_lists` maps aliases (e.g. `omegapoint`) to list
IDs so agents don't need discovery calls.

## Behavioral contracts (don't break these)

Full rationale in `AGENT.md` → "Architecture decisions". The headlines:

- JSON to stdout, errors to stderr, no spinners — agents pipe stdout.
- `--format` is global (root callback), never per-command.
- Updates are modify-if-passed: only explicitly passed fields change;
  `--description ""` clears.
- Destructive ops never prompt; they require `--force`/`--yes` or exit 2.
- Rich markup is escaped on all user data (`[bug] foo` must survive).

## Testing

- `tests/unit/` — mocked, fast.
- `tests/integration/` — mocked end-to-end CLI invocations.
- `tests/live/` — `@pytest.mark.live`, hits real ClickUp (`just test-live`).
- `.claude/skills/cli-agent-eval` — 12-task agent swarm regression eval; run
  after non-trivial CLI changes.
- `just fc` before every commit (format + lint + type + test).

## Related repos

- **[EvanOman/planka-deploy](https://github.com/EvanOman/planka-deploy)**
  (private) — runs the Planka backend: Railway infra, Caddy proxy, backups,
  local compose stack, seed data. This repo deliberately contains no
  deployment code.
