#!/usr/bin/env bash
# teardown.sh — gracefully end a pilot. Preserves logs + .env for audit.
#
# Usage:
#   ./teardown.sh --client-id acme

set -euo pipefail

CLIENT_ID=""
DELETE_DATA=0
USAGE="Usage: $0 --client-id <name> [--delete-data]"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client-id)   CLIENT_ID="$2"; shift 2 ;;
    --delete-data) DELETE_DATA=1;  shift ;;
    -h|--help)     echo "$USAGE"; exit 0 ;;
    *)             echo "unknown arg: $1" >&2; echo "$USAGE" >&2; exit 1 ;;
  esac
done
[[ -z "$CLIENT_ID" ]] && { echo "$USAGE" >&2; exit 1; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLIENT_DIR="$SCRIPT_DIR/clients/$CLIENT_ID"

if [[ ! -d "$CLIENT_DIR" ]]; then
  echo "no client directory at $CLIENT_DIR — nothing to tear down" >&2
  exit 1
fi

echo "▸ Stopping stack for $CLIENT_ID..."
(cd "$CLIENT_DIR" && docker compose --env-file .env down) || true

# Archive logs so they survive
TS=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="$CLIENT_DIR/logs-${TS}.tar.gz"
if [[ -d "$CLIENT_DIR/logs" ]]; then
  tar -czf "$ARCHIVE" -C "$CLIENT_DIR" logs/ 2>/dev/null || true
  echo "✓ Logs archived to: $ARCHIVE"
fi

if [[ $DELETE_DATA -eq 1 ]]; then
  echo "▸ Removing volumes (cache data)..."
  (cd "$CLIENT_DIR" && docker compose --env-file .env down -v) || true
fi

echo "✓ Teardown complete. Audit trail preserved at: $CLIENT_DIR"
echo "  (Use --delete-data to also drop the Redis volume.)"
