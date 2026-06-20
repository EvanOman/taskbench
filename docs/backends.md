# Backends: how to run the CLI against each provider

The CLI talks to backends through the `TaskProvider` port
(`taskbench/core/providers.py`). Select a backend with the `TASKBENCH_PROVIDER`
env var (legacy `CLICKUP_PROVIDER` still works with a deprecation warning),
or the `provider` config key:

| `TASKBENCH_PROVIDER` | Adapter | Needs infra? | Use for |
|---|---|---|---|
| `clickup` (default) | `taskbench/core/client.py` | No (SaaS) | Real ClickUp workspaces |
| `json` (aliases: `local`, `mock`) | `taskbench/core/json_provider.py` | **No — zero setup** | Development, evals, offline testing |
| `generic` | planned — see `spec/README.md` | Yes (any spec-conformant server) | Non-Python backends |

External adapters are discovered via `entry_points(group="taskbench.providers")`.
See `docs/writing-an-adapter.md` for how to write one.

Verify any backend with:

```bash
uv run taskbench status              # auth + config check
uv run taskbench discover hierarchy  # walk workspace -> space -> list
```

---

## json — zero-infra local backend (start here)

No credentials, no network, no containers. Ideal when developing the CLI
itself or testing agent workflows.

```bash
export TASKBENCH_PROVIDER=json
uv run taskbench discover hierarchy
uv run taskbench task list --list-id <id from discover>
```

- State lives in a single JSON file: `~/.config/taskbench/mock-store.json`
  (created with a deterministic seed workspace on first use).
- Point at a different store with `CLICKUP_JSON_STORE=/path/to/store.json` —
  use a throwaway path in tests/evals so you don't clobber other runs.
- The seed workspace has statuses `to do / in progress / on-deck / complete`.

## clickup — the real SaaS (default)

```bash
export CLICKUP_API_KEY=pk_...        # or CLICKUP_API_TOKEN
uv run taskbench status
```

- Token priority: env var > persisted config (`~/.config/taskbench/config.json`).
- First-time interactive setup: `uv run taskbench setup run`
  (agents: pass `--token/--team-id/--space-id/--list-id/--non-interactive`).
- `.env` files are auto-loaded from `~/.config/taskbench/.env` and the
  current working directory.

## generic — bring your own backend (planned)

`spec/openapi.yaml` defines the REST contract. Implement it (any language)
and the planned `GenericProvider` will drive it via `TASKBACKEND_URL` +
`TASKBACKEND_TOKEN`. Until that adapter lands, the spec is the design target
for new shims; see `spec/README.md` for conformance levels.
