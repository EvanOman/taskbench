# Postgres backup service

Standalone Railway service that runs `pg_dump` on a daily cron and stores
gzipped dumps in its own persistent volume. Separate volume from the live
Postgres so a Postgres-volume incident can't take the backups with it.

## Why this exists

While diagnosing the Caddy + image-pinning round 2 deploy, we discovered the
hard way that **changing the Postgres service's `source.image` field in
Railway can render the volume's data inaccessible to the new container**
(the volume itself wasn't deleted, but the new Postgres instance saw a fresh
empty data dir and re-initialized). We re-seeded from `seed.py` and lost
nothing real, but on a deployment with real user data that would be unrecoverable
without backups.

Railway has native volume backups, but they require Pro. This is the free
alternative.

## What it does

- Service image: `postgres:15-alpine` (same major as the live DB; ships
  with `pg_dump` + `psql`)
- `cronSchedule`: `0 4 * * *` (04:00 UTC daily) — the service spins up,
  runs `backup.sh`, exits
- Volume: dedicated `db-backups` mounted at `/backups` — NOT the same
  volume as the live Postgres
- Retention: keeps the 30 most recent dumps (configurable via `RETENTION`)
- Network: dumps the live Postgres over Railway's private DNS at
  `postgres.railway.internal:5432`

## Bootstrap (run once, after the rest of the project is up)

```bash
source .secrets/railway-deploy.env
TOKEN="$RAILWAY_API_TOKEN"

# Create the backup service (postgres:15-alpine, digest-pinned)
BACKUP_SVC=$(curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -nc \
    --arg pid "$PROJECT_ID" --arg eid "$ENV_ID" \
    --arg pw "$POSTGRES_PASSWORD" \
    --rawfile script deploy/railway/backup/backup.sh \
    --argjson vars '{"DB_HOST":"postgres.railway.internal","DB_PORT":"5432","DB_NAME":"planka","DB_USER":"planka","BACKUPS_DIR":"/backups","RETENTION":"30"}' \
    '{
       query: "mutation($input: ServiceCreateInput!) { serviceCreate(input: $input) { id name } }",
       variables: { input: {
         projectId: $pid, environmentId: $eid, name: "db-backup",
         source: { image: "postgres:15-alpine" },
         variables: ($vars + {DB_PASSWORD: $pw, BACKUP_SCRIPT: $script})
       } }
     }')" | jq -r '.data.serviceCreate.id')

# Add backups volume
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -nc --arg pid "$PROJECT_ID" --arg eid "$ENV_ID" --arg sid "$BACKUP_SVC" \
    '{query: "mutation($input: VolumeCreateInput!) { volumeCreate(input: $input) { id name } }",
      variables: { input: { projectId: $pid, environmentId: $eid, serviceId: $sid, mountPath: "/backups" } }}')"

# Configure cron + startCommand
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -nc --arg eid "$ENV_ID" --arg sid "$BACKUP_SVC" '{
       query: "mutation($eid: String!, $sid: String!, $input: ServiceInstanceUpdateInput!) {
         serviceInstanceUpdate(environmentId: $eid, serviceId: $sid, input: $input)
       }",
       variables: { eid: $eid, sid: $sid, input: {
         cronSchedule: "0 4 * * *",
         startCommand: "sh -c '"'"'echo \"$BACKUP_SCRIPT\" > /tmp/backup.sh && chmod +x /tmp/backup.sh && /tmp/backup.sh'"'"'"
       } }
     }')"
```

## Manual backup before risky operations

**Before** any of the following, take a manual backup:

- Changing the Postgres service's `source.image` (tag or digest)
- Changing `PGDATA` or other Postgres env vars
- Changing the postgres volume's `mountPath`
- Migrating to a different Postgres major version
- Editing the Postgres service in the Railway dashboard (any UI change that
  causes a redeploy can potentially affect the volume)

To trigger a backup on demand:

```bash
# Option A: Restart the db-backup service. cron triggers run on the schedule;
# you can also just hit the redeploy endpoint to run once now.
~/.railway/bin/railway redeploy --service db-backup
# (then check the deploy logs to confirm the backup completed)

# Option B: From a workstation that can talk to the Railway API:
source .secrets/railway-deploy.env
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -nc --arg eid "$ENV_ID" --arg sid "$BACKUP_SVC" \
    '{query: "mutation { serviceInstanceRedeploy(environmentId: \"\($eid)\", serviceId: \"\($sid)\") }"}')"
```

## Restore from a backup

The restore writes into the live Postgres database. **It overwrites what's there.**

```bash
# 1) Connect to the live Postgres via railway shell or psql with the password
#    from .secrets/railway-deploy.env

# 2) List available backups
~/.railway/bin/railway run --service db-backup ls -lh /backups/

# 3) Restore — replace <FILE> with the actual dump filename
~/.railway/bin/railway run --service db-backup \
  sh -c 'BACKUP_FILE=/backups/<FILE> /tmp/restore.sh'

# 4) Redeploy Planka so it reconnects cleanly
~/.railway/bin/railway redeploy --service planka

# 5) Verify the data is back via CLI
export CLICKUP_PROVIDER=planka PLANKA_URL=... PLANKA_PASSWORD=...
uv run clickup discover hierarchy
```

## What the backup contains

`pg_dump --no-owner --no-acl --clean --if-exists` of the `planka` database.
Restores cleanly into a fresh cluster — including dropping/recreating any
existing schema. No Postgres-server config is captured (that's set via env
vars on the postgres service).

## What this does NOT protect against

- **Planka's `/app/private` volume contents** — card attachments, avatars,
  background images. These live on the planka service's volume, not in
  Postgres. If you start using attachments heavily, add a second backup
  service that snapshots `/app/private`.
- **Railway region outage** — backups live in the same Railway region as
  the live DB. For region-redundant backups, periodically copy backup files
  out to a different provider (Backblaze B2 free tier, etc.).
- **A leaked admin token** that deletes the project — Railway has a
  "trash" / recovery window of ~30 days for deleted projects, but don't
  rely on it.
