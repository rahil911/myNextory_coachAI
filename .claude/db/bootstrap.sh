#!/usr/bin/env bash
# bootstrap.sh — Recreate the baap MariaDB database from the compressed dump.
#
# Usage:
#   bash .claude/db/bootstrap.sh
#
# Prerequisites:
#   - MariaDB or MySQL server running locally
#   - mysql client on PATH
#   - User must have CREATE DATABASE privileges
#
# This script is idempotent — safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DUMP="$SCRIPT_DIR/baap.sql.gz"

if [ ! -f "$DUMP" ]; then
    echo "ERROR: Dump not found at $DUMP"
    exit 1
fi

echo "Creating database 'baap' (if not exists)..."
mysql -e "CREATE DATABASE IF NOT EXISTS baap CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "Loading dump ($DUMP)..."
gunzip -c "$DUMP" | mysql baap

echo "Verifying..."
TABLE_COUNT=$(mysql baap -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='baap';")
echo "Done. $TABLE_COUNT tables loaded in 'baap' database."
