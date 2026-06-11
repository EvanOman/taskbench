# Backends: how to run the CLI against each provider

The CLI talks to backends through the `TaskProvider` port
(`clickup/core/providers.py`). Select a backend with the `CLICKUP_PROVIDER`
env var (or the `provider` config key):

| `CLICKUP_PROVIDER` | Adapter | Needs infra? | Use for |
|---|---|---|---|
| `clickup` (default) | `clickup/core/client.py` | No (SaaS) | Real ClickUp workspaces |
| `json` (aliases: `local`, `mock`) | `clickup/core/json_provider.py` | **No — zero setup** | Development, evals, offline testing |
| `planka` | `clickup/core/planka_provider.py` | Yes (self-hosted Kanban) | Open-source backend |
| `generic` | planned — see `spec/README.md` | Yes (any spec-conformant server) | Non-Python backends |

Verify any backend with:

```bash
uv run clickup status              # auth + config check
uv run clickup discover hierarchy  # walk workspace -> space -> list
```

---

## json — zero-infra local backend (start here)

No credentials, no network, no containers. Ideal when developing the CLI
itself or testing agent workflows.

```bash
export CLICKUP_PROVIDER=json
uv run clickup discover hierarchy
uv run clickup task list --list-id <id from discover>
```

- State lives in a single JSON file: `~/.config/clickup-toolkit/mock-store.json`
  (created with a deterministic seed workspace on first use).
- Point at a different store with `CLICKUP_JSON_STORE=/path/to/store.json` —
  use a throwaway path in tests/evals so you don't clobber other runs.
- The seed workspace has statuses `to do / in progress / on-deck / complete`.

## clickup — the real SaaS (default)

```bash
export CLICKUP_API_KEY=pk_...        # or CLICKUP_API_TOKEN
uv run clickup status
```

- Token priority: env var > persisted config (`~/.config/clickup-toolkit/config.json`).
- First-time interactive setup: `uv run clickup setup run`
  (agents: pass `--token/--team-id/--space-id/--list-id/--non-interactive`).
- `.env` files are auto-loaded from `~/.config/clickup-toolkit/.env` and the
  current working directory.

## planka — self-hosted Kanban

The adapter maps Planka's model onto the task hierarchy:
project→space, board→list, column→status, card→task. Folders are synthetic
(`folder_<spaceId>`); `raw_request` is unsupported.

Env vars (read by `planka_provider.py`):

| Var | Default | Notes |
|---|---|---|
| `PLANKA_URL` | `http://localhost:18920` | Base URL of the Planka instance |
| `PLANKA_EMAIL` (or `PLANKA_USERNAME`) | `admin` | Login identity |
| `PLANKA_PASSWORD` | — (required) | Login password |

### Option A: the live deployment (Railway)

Deployment and ops live in the **private repo
[EvanOman/planka-deploy](https://github.com/EvanOman/planka-deploy)**
(locally at `/home/evan/dev/planka-deploy` on Evan's machine).

```bash
export CLICKUP_PROVIDER=planka
export PLANKA_URL=https://caddy-production-5cac.up.railway.app
export PLANKA_EMAIL=admin@taskflow.cloud
export PLANKA_PASSWORD=...   # PLANKA_ADMIN_PASSWORD in planka-deploy/.secrets/railway-deploy.env
uv run clickup discover hierarchy
```

### Option B: spin up Planka locally

```bash
docker compose -f /home/evan/dev/planka-deploy/local/docker-compose.yml up -d
# wait ~15s for first boot, then:
export CLICKUP_PROVIDER=planka
export PLANKA_EMAIL=admin@local
export PLANKA_PASSWORD='Planka!Admin2025#Secure'   # local-only default, see compose file
uv run clickup status
```

The local instance serves on `http://localhost:18920` (the adapter's default
URL, so `PLANKA_URL` can be omitted). To populate it with the canonical
25-task TaskFlow dataset: `uv run /home/evan/dev/planka-deploy/seed/seed.py`.

Tear down with `docker compose -f .../local/docker-compose.yml down`
(add `-v` to also wipe data).

### No access to planka-deploy?

Use the `json` provider — it exercises the same CLI surface with zero infra.
The planka adapter itself only needs *any* reachable Planka instance
(`ghcr.io/plankanban/planka` on Docker Hub) plus the three env vars above.

## generic — bring your own backend (planned)

`spec/openapi.yaml` defines the REST contract. Implement it (any language)
and the planned `GenericProvider` will drive it via `TASKBACKEND_URL` +
`TASKBACKEND_TOKEN`. Until that adapter lands, the spec is the design target
for new shims; see `spec/README.md` for conformance levels.
