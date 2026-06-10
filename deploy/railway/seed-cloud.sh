#!/usr/bin/env bash
# Seed the Railway-deployed Planka with the canonical 25-task TaskFlow dataset.
#
# Usage:
#   # Option 1: source a .env.cloud file (gitignored)
#   source .env.cloud && ./deploy/railway/seed-cloud.sh
#
#   # Option 2: pass env vars inline
#   PLANKA_URL=https://planka-xxx.up.railway.app \
#   PLANKA_PASSWORD='...' \
#     ./deploy/railway/seed-cloud.sh
#
# Prerequisites:
#   - uv installed
#   - Run from the repo root (or the adapter-planka worktree root)

set -euo pipefail

: "${PLANKA_URL:?Set PLANKA_URL to the Railway Planka URL}"
: "${PLANKA_PASSWORD:?Set PLANKA_PASSWORD to the admin password}"

# Defaults matching the Railway deploy config
export PLANKA_URL
export PLANKA_USERNAME="${PLANKA_USERNAME:-admin}"
export PLANKA_PASSWORD

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Seeding Planka at $PLANKA_URL ..."
cd "$REPO_ROOT"
uv run python seed.py

echo ""
echo "Done. Verify with:"
echo "  CLICKUP_PROVIDER=planka PLANKA_URL=$PLANKA_URL \\"
echo "  PLANKA_EMAIL=admin@taskflow.cloud PLANKA_PASSWORD=\$PLANKA_PASSWORD \\"
echo "  uv run clickup discover hierarchy"
