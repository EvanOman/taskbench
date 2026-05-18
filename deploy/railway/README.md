# Planka on Railway

Deploy the Planka Kanban board to [Railway](https://railway.com) for the clickup-tools adapter evaluation.

## Deployed URL

> **TBD** — set after initial deployment (e.g. `https://planka-prod-xxxx.up.railway.app`)

## Cost expectations

Railway's free trial includes **$5 of credit** with no credit card required.
Planka + Postgres idle usage is roughly **$2-4/month**, so the trial should last
**1-2 months** of light use. The deployment **will pause automatically** when the
credit is consumed — no surprise charges.

To continue after the trial, add a credit card and upgrade to the Hobby plan ($5/month).

## Architecture

Two Railway services in a single project (`clickup-tools-planka`):

| Service | Type | Notes |
|---------|------|-------|
| **Postgres** | Railway managed add-on | Automatic backups, shared `DATABASE_URL` variable |
| **Planka** | Docker image `ghcr.io/plankanban/planka:latest` | Persistent volume at `/app/private` for uploads |

## Bootstrap from scratch

If you need to recreate the project (e.g. after deleting it):

### 1. Sign up / log in

```bash
# Install Railway CLI
curl -sSL https://railway.com/install.sh | sh

# Browserless login (generates a code to enter at railway.com/activate)
railway login --browserless
```

Or sign up at https://railway.com with GitHub or email.

### 2. Create the project

```bash
railway init --name clickup-tools-planka
```

### 3. Add Postgres

```bash
railway add --database postgres
```

### 4. Add Planka service from Docker image

```bash
railway add --image ghcr.io/plankanban/planka:latest --service planka
```

### 5. Add a persistent volume

In the Railway dashboard, select the Planka service and add a volume:
- **Mount path:** `/app/private`
- **Size:** 1 GB (default)

> Note: Volumes cannot be added via CLI as of Railway CLI v4.x.

### 6. Configure environment variables

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
export PLANKA_URL=https://planka-prod-xxxx.up.railway.app
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
export PLANKA_URL=https://planka-prod-xxxx.up.railway.app
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
p = Planka("https://planka-prod-xxxx.up.railway.app")
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
