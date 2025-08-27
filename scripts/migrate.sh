#!/usr/bin/env bash
# Usage: ./migrate.sh [CONTAINER_NAME] [DB_NAME] [DB_USER] [MIG_DIR]
# Defaults: CONTAINER_NAME=jl_postgres, DB_NAME=joblink, DB_USER=joblink, MIG_DIR=../db/init
set -euo pipefail

CONTAINER="${1:-joblink-db-1}"
DB="${2:-joblink}"
USER="${3:-joblink}"
# If MIG_DIR provided as 4th arg use it, else default to repo-relative ../db/init
DEFAULT_MIG_DIR="$(cd "$(dirname "$0")" && pwd)/../db/init"
MIG_DIR="${4:-$DEFAULT_MIG_DIR}"

if [ ! -d "$MIG_DIR" ]; then
  echo "Migration directory not found: $MIG_DIR" >&2
  exit 2
fi

# Ensure container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Container ${CONTAINER} not running. Start with 'docker compose up -d'." >&2
  exit 3
fi

shopt -s nullglob
files=("$MIG_DIR"/*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "No .sql files found in $MIG_DIR" >&2
  exit 4
fi

# Apply in lexical order: 01_*.sql, 02_*.sql, ...
for f in "${files[@]}"; do
  bn="$(basename "$f")"
  echo "Applying $bn"
  docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" < "$f"
done

echo "Migrations completed."
