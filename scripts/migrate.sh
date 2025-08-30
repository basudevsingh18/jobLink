#!/usr/bin/env bash
# Usage:
#   ./migrate.sh [CONTAINER_NAME] [DB_NAME] [DB_USER] [MIG_DIR]
# Defaults:
#   CONTAINER_NAME=microjobs-db-1
#   DB_NAME=joblink
#   DB_USER=joblink
#   MIG_DIR=../db/init  (relative to this script)

set -Eeuo pipefail

CONTAINER="${1:-microjobs-db-1}"
DB="${2:-joblink}"
USER="${3:-joblink}"
DEFAULT_MIG_DIR="$(cd "$(dirname "$0")" && pwd)/../db/init"
MIG_DIR="${4:-$DEFAULT_MIG_DIR}"

# Pretty echo helpers
info()  { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
error() { printf "\033[1;31m[FAIL]\033[0m %s\n" "$*" >&2; }

# On error, say which file we were applying
current_file=""
trap '[[ -n "$current_file" ]] && error "Failed while applying: $current_file"' ERR

# Checks
if [ ! -d "$MIG_DIR" ]; then
  error "Migration directory not found: $MIG_DIR"
  exit 2
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  error "Container ${CONTAINER} not running. Start with: docker compose up -d"
  exit 3
fi

# Optional: verify psql exists in the container
if ! docker exec "$CONTAINER" sh -lc 'command -v psql >/dev/null 2>&1'; then
  error "psql not found in container ${CONTAINER}."
  warn "Are you sure this is the Postgres container? (image: postgres:*)"
  exit 4
fi

# Collect .sql files (lexical order). Recommend having:
#  00_extensions.sql, 01_tables.sql, 02_indexes.sql, 03_triggers.sql, 04_functions.sql, 05_rls_policies.sql, 06_seeds.sql
# Collect .sql files (lexical order)
shopt -s nullglob
files=($(ls "$MIG_DIR"/*.sql 2>/dev/null | sort))
if [ ${#files[@]} -eq 0 ]; then
  error "No .sql files found in $MIG_DIR"
  exit 5
fi


info "Applying ${#files[@]} migration files to ${DB} as ${USER} (container: ${CONTAINER})"
info "Directory: $MIG_DIR"

# If your DB requires a password inside the container, set POSTGRES_PASSWORD env
# e.g. docker exec -e PGPASSWORD=...  (we only add it if present on host)
PGPASS_ENV=()
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  PGPASS_ENV=(-e "PGPASSWORD=${POSTGRES_PASSWORD}")
fi

for f in "${files[@]}"; do
  bn="$(basename "$f")"
  current_file="$bn"
  info "Applying $bn"
  # -X: no .psqlrc
  # -1: wrap file in a single transaction
  # -v ON_ERROR_STOP=1: stop on first error in the file
  # -q: quiet psql chatter (keeps errors visible)
  docker exec -i "${PGPASS_ENV[@]}" "$CONTAINER" \
    psql -X -v ON_ERROR_STOP=1 -1 -q -U "$USER" -d "$DB" < "$f"
done

current_file=""
info "Migrations completed successfully."
