#!/usr/bin/env bash
# Apply only seed files matching *seed*.sql
set -euo pipefail
CONTAINER="${1:-joblink-db-1}"
DB="${2:-joblink}"
USER="${3:-joblink}"
MIG_DIR="${4:-$(cd "$(dirname "$0")"/.. && pwd)/db/init}"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Container ${CONTAINER} not running." >&2
  exit 3
fi

shopt -s nullglob
files=("$MIG_DIR"/*seed*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "No seed files found in $MIG_DIR" >&2
  exit 4
fi

for f in "${files[@]}"; do
  echo "Seeding $(basename "$f")"
  docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" < "$f"
done

echo "Seeding completed."
