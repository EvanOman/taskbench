# Planka on Railway

Deploy the Planka Kanban board to [Railway](https://railway.com) for the clickup-tools adapter evaluation.

## Deployed URL

**Live:** [https://caddy-production-5cac.up.railway.app](https://caddy-production-5cac.up.railway.app)

> The public entrypoint is a **Caddy reverse proxy** that injects security
> headers. The Planka container itself is no longer publicly exposed — it only
> answers traffic from Caddy via Railway's private network. See `caddy/` for
> the proxy config and what it closes from the security audit.

Admin login: `admin` / *(password lives in Railway env vars only — see `.secrets/railway-deploy.env` locally)*

## Cost expectations

Railway's free trial includes **$5 of credit** with no credit card required.
Planka + Postgres idle usage is roughly **$2-4/month**, so the trial should last
**1-2 months** of light use. The deployment **will pause automatically** when the
credit is consumed — no surprise charges.

To continue after the trial, add a credit card and upgrade to the Hobby plan ($5/month).

## Architecture

Four Railway services in a single project (`clickup-tools-planka`):

| Service | Type | Public? | Notes |
|---------|------|---------|-------|
| **caddy** | `caddy@sha256:…` (digest-pinned) | **Yes** (port 80) | Reverse proxy; injects security headers; only public entrypoint. Config in `caddy/Caddyfile`, shipped to Railway via `CADDYFILE_CONTENT` env var. |
| **planka** | `ghcr.io/plankanban/planka@sha256:…` (digest-pinned) | No | Internal-only at `planka.railway.internal:1337`. Persistent volume at `/app/private`. |
| **postgres** | `postgres@sha256:…` (digest-pinned, 15.18) | No | Internal-only at `postgres.railway.internal:5432`. Persistent volume at `/var/lib/postgresql/data`. |
| **db-backup** | `postgres@sha256:…` (same digest as live postgres) | No | Daily `pg_dump` to its own `/backups` volume. Cron `0 4 * * *`. See `backup/README.md`. |

Caddy is what closes the bulk of the security audit's medium-severity findings
(see `caddy/README.md` for the full list). Planka being internal-only means the
only attack surface is Caddy + Railway's edge.

---

## Data safety — read this before redeploying

During the audit work we hit a data wipe: pinning the Postgres image source
caused Planka to see an empty database after the redeploy. The volume was
still attached; the data inside was no longer accessible to the new Postgres
container (likely a Railway mount-race or permission shift on image source
change). We re-seeded — on real data this would have been unrecoverable.

To prevent recurrence, the project now runs a **`db-backup` service** that
takes a `pg_dump` of the live database daily at 04:00 UTC and stores 30 days
of dumps on its own dedicated volume (not the Postgres volume). See
`backup/README.md` for the bootstrap, restore procedure, and limitations.

### Operations that REQUIRE a manual backup first

Before doing any of these, trigger a manual backup and confirm the dump file
appeared in `/backups`:

- Changing the Postgres service's `source.image` (tag or digest)
- Editing `PGDATA` / `POSTGRES_USER` / `POSTGRES_DB` / `POSTGRES_PASSWORD`
- Changing the postgres volume's `mountPath`
- Migrating to a different Postgres major version
- Deleting and recreating the Postgres service (volume is decoupled — orphan happens)
- Anything in the Railway dashboard that triggers a Postgres redeploy

Manual backup trigger:

```bash
source .secrets/railway-deploy.env
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" -H "Content-Type: application/json" \
  -d "{\"query\":\"mutation { serviceInstanceRedeploy(environmentId: \\\"$ENV_ID\\\", serviceId: \\\"$BACKUP_SVC\\\") }\"}"
# Wait ~30s, then verify the new dump landed:
~/.railway/bin/railway logs --service db-backup | tail -5
```

### What CI's auto-deploy can and cannot touch

`.github/workflows/deploy-planka-railway.yml` is path-filtered to
`deploy/railway/**` and `planka-stack/**`, and only redeploys the **planka**
service (`railway redeploy --service planka`). It never touches `postgres`
or `db-backup`. **Don't change the workflow to redeploy postgres** — keep
all postgres operations behind the manual-backup-first checklist above.

## Bootstrap from scratch

If you need to recreate the project (e.g. after deleting it):

### 1. Sign up at Railway

Sign up at https://railway.com with GitHub OAuth (cleanest path — Railway gets your verified identity from GitHub and skips email/phone verification).

> **Heads up:** Railway's login UI is protected by Cloudflare Turnstile, which defeats headless browser automation. Signup is a manual one-time step. The rest of provisioning is fully scriptable.

### 2. Get an API token

Go to https://railway.com/account/tokens and create a personal token. Note: the CLI's `railway login --browserless` requires an interactive TTY which isn't always available — the API token path is more reliable for automation.

```bash
export RAILWAY_API_TOKEN=<your-token>
```

### 3. Create the project via API

The CLI's `whoami` query may fail with some token types, but the GraphQL API works. Project creation:

```bash
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { projectCreate(input: {name: \"clickup-tools-planka\"}) { id name } }"}'
```

Save the returned project ID.

### 4. Add Postgres + Planka services with env vars inline

**Important:** Create services with all env variables set inline (in `ServiceCreateInput.variables`). Editing variables after creation triggers redeploys, and if Planka has already created the default admin user, the next redeploy will crash trying to re-insert it. Set everything in one shot.

See `deploy/railway/bootstrap.sh` (or the seed script below) for the exact GraphQL calls. Required env vars per service:

| Service | Env vars |
|---------|----------|
| Postgres | `POSTGRES_DB=planka`, `POSTGRES_USER=planka`, `POSTGRES_PASSWORD=<random>`, `PGDATA=/var/lib/postgresql/data/pgdata` |
| Planka | All vars in `planka.env.example` |

### 5. Add persistent volumes

Both services need volumes:

| Service | Mount path |
|---------|------------|
| Postgres | `/var/lib/postgresql/data` |
| Planka | `/app/private` |

Add via the `volumeCreate` GraphQL mutation, or in the Railway dashboard under each service's Settings → Volumes.

### 6. Set up the Caddy reverse proxy

Planka itself should NOT have a public domain — only Caddy. Create a `caddy`
service from `caddy:2-alpine`, set `CADDYFILE_CONTENT` to the contents of
`caddy/Caddyfile`, override `startCommand` to materialize the Caddyfile at
runtime, then add a public domain at port 80 to the caddy service:

```sh
# startCommand
sh -c 'echo "$CADDYFILE_CONTENT" > /etc/caddy/Caddyfile && caddy run --config /etc/caddy/Caddyfile --adapter caddyfile'
```

Finally, set `BASE_URL=https://<caddy-domain>` on the Planka service so its
generated absolute URLs reference the public entrypoint.

See `caddy/README.md` for what the proxy closes from the security audit.

In the Railway dashboard, set these on the **Planka** service:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway shared variable) |
| `BASE_URL` | The public URL Railway assigns (e.g. `https://planka-prod-xxxx.up.railway.app`) |
| `SECRET_KEY` | `openssl rand -hex 64` |
| `DEFAULT_ADMIN_EMAIL` | `admin@taskflow.cloud` |
| `DEFAULT_ADMIN_PASSWORD` | Generate a strong password. **Do NOT commit this.** |
| `DEFAULT_ADMIN_NAME` | `Admin` |
| `DEFAULT_ADMIN_USERNAME` | `admin` |
| `TRUST_PROXY` | `1` |

The admin password lives **only** in Railway's environment variables — never in this repo.

### 7. Deploy

Railway auto-deploys on config changes. Verify at the assigned URL.

### 8. Generate a project token (for CI)

In the Railway dashboard: **Project Settings > Tokens > Create Token**.
This is a **project-scoped** token (not account-level).

```bash
gh secret set RAILWAY_TOKEN --body "<token>" --repo EvanOman/clickup-tools
```

## Seed the board

After the deployment is live, populate it with the 25-task TaskFlow dataset:

```bash
# From the repo root (or adapter-planka worktree root)
export PLANKA_URL=https://caddy-production-5cac.up.railway.app
export PLANKA_PASSWORD='<admin password from Railway env vars>'
./deploy/railway/seed-cloud.sh
```

Or directly:

```bash
PLANKA_URL=https://... PLANKA_PASSWORD='...' uv run python seed.py
```

## Verify via CLI

```bash
export CLICKUP_PROVIDER=planka
export PLANKA_URL=https://caddy-production-5cac.up.railway.app
export PLANKA_EMAIL=admin@taskflow.cloud
export PLANKA_PASSWORD='...'

uv run clickup discover hierarchy
uv run clickup task list --list-id <board-id>
```

## Wipe all data

Option A — Delete the project in Railway dashboard.

Option B — Delete all Planka projects via the API:

```python
from plankapy.v2 import Planka
p = Planka("https://caddy-production-5cac.up.railway.app")
p.login(username="admin", password="...", accept_terms=True)
for proj in p.projects:
    proj.delete()
```

## Redeploy

- **Automatic:** Push to `master` with changes in `deploy/railway/**` or `planka-stack/**` triggers the GitHub Actions workflow.
- **Manual:** Go to Actions > "Deploy Planka to Railway" > Run workflow.
- **CLI:** `railway redeploy --service planka`

## Files

| Path | Purpose |
|------|---------|
| `deploy/railway/railway.toml` | Declarative Railway service config |
| `deploy/railway/planka.env.example` | All required env vars (no secrets) |
| `deploy/railway/seed-cloud.sh` | Wrapper to seed the cloud Planka |
| `deploy/railway/README.md` | This file |
| `.github/workflows/deploy-planka-railway.yml` | CI/CD workflow |
