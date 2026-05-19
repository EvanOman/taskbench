#!/bin/sh
# Postgres restore script — used to restore from a backup created by backup.sh.
# Image: postgres:15-alpine
#
# Usage in Railway shell:
#   BACKUP_FILE=/backups/planka-YYYYMMDD-HHMMSS.sql.gz ./restore.sh
#
# Required env vars (set in Railway):
#   DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
#   BACKUP_FILE  — full path to the .sql.gz dump to restore from
#
# WARNING: this OVERWRITES the target database. Don't restore without
# confirming the target is what you expect.

set -eu

: "${DB_HOST:?missing}"
: "${DB_PORT:=5432}"
: "${DB_NAME:?missing}"
: "${DB_USER:?missing}"
: "${DB_PASSWORD:?missing}"
: "${BACKUP_FILE:?must specify BACKUP_FILE=/backups/planka-...sql.gz}"

[ -f "$BACKUP_FILE" ] || { echo "ERROR: $BACKUP_FILE does not exist"; exit 1; }

echo "[$(date -u +%FT%TZ)] restore: target $DB_NAME on $DB_HOST"
echo "[$(date -u +%FT%TZ)] restore: source $BACKUP_FILE ($(stat -c%s "$BACKUP_FILE" 2>/dev/null || wc -c < "$BACKUP_FILE") bytes)"

# Dump uses --clean --if-exists so it drops + recreates objects before inserting.
# We pipe through psql against the target db.
gunzip -c "$BACKUP_FILE" \
  | PGPASSWORD="$DB_PASSWORD" psql \
      -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
      --set ON_ERROR_STOP=on \
      --quiet

echo "[$(date -u +%FT%TZ)] restore: done"
echo "[$(date -u +%FT%TZ)] restore: verify with: PGPASSWORD=... psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c '\\dt'"
