#!/bin/sh
# Postgres backup script — runs in the db-backup Railway service.
# Image: postgres:15-alpine (has pg_dump + gzip).
# Triggered by Railway cron OR manually via `railway run`.
#
# Required env vars (set in Railway):
#   DB_HOST       = postgres.railway.internal
#   DB_PORT       = 5432
#   DB_NAME       = planka
#   DB_USER       = planka
#   DB_PASSWORD   = (mirror of POSTGRES_PASSWORD on the postgres service)
#   BACKUPS_DIR   = /backups   (mounted Railway volume)
#   RETENTION     = 30         (keep N most recent dumps)

set -eu

: "${DB_HOST:?missing}"
: "${DB_PORT:=5432}"
: "${DB_NAME:?missing}"
: "${DB_USER:?missing}"
: "${DB_PASSWORD:?missing}"
: "${BACKUPS_DIR:=/backups}"
: "${RETENTION:=30}"

mkdir -p "$BACKUPS_DIR"

TS="$(date -u +%Y%m%d-%H%M%S)"
OUT="$BACKUPS_DIR/planka-${TS}.sql.gz"

echo "[$(date -u +%FT%TZ)] backup: dumping $DB_NAME from $DB_HOST -> $OUT"

# Use --no-owner --no-acl so dumps restore cleanly into a fresh cluster.
# Use --clean --if-exists so restoring overwrites whatever's there.
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
  --no-owner --no-acl --clean --if-exists \
  "$DB_NAME" \
  | gzip -9 > "$OUT"

SIZE=$(stat -c%s "$OUT" 2>/dev/null || wc -c < "$OUT")
echo "[$(date -u +%FT%TZ)] backup: wrote $OUT ($SIZE bytes)"

# Rotation: keep only the N most recent
TO_REMOVE=$(ls -t "$BACKUPS_DIR"/planka-*.sql.gz 2>/dev/null | tail -n +"$((RETENTION + 1))" || true)
if [ -n "$TO_REMOVE" ]; then
	echo "[$(date -u +%FT%TZ)] backup: rotating out $(echo "$TO_REMOVE" | wc -l) old dumps"
	echo "$TO_REMOVE" | xargs -r rm -f
fi

echo "[$(date -u +%FT%TZ)] backup: current dumps:"
ls -lh "$BACKUPS_DIR"/planka-*.sql.gz 2>/dev/null || echo "  (none)"

echo "[$(date -u +%FT%TZ)] backup: done"
