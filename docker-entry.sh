#!/usr/bin/env bash
set -euo pipefail

if [ -z "${PGRST_DB_URI:-}" ]; then
  echo "ERROR: PGRST_DB_URI is not set. Set it to your Postgres connection string."
  exit 1
fi

echo "==> Waiting for database to be reachable..."
TRIES=0
until psql "${PGRST_DB_URI}" -c "select 1" >/dev/null 2>&1; do
  TRIES=$((TRIES+1))
  if [ "$TRIES" -gt 30 ]; then
    echo "Database not reachable after 30s. Exiting."
    exit 1
  fi
  sleep 1
done
echo "==> Database OK"

echo "==> Applying migrations (idempotent)..."
if [ -d "/app/db/init" ]; then
  for f in /app/db/init/*.sql; do
    [ -e "$f" ] || continue
    echo "   -> $(basename "$f")"
    psql "${PGRST_DB_URI}" -v ON_ERROR_STOP=1 -f "$f"
  done
fi

echo "==> Applying seeds (idempotent)..."
if [ -d "/app/db/seed" ]; then
  for f in /app/db/seed/*.sql; do
    [ -e "$f" ] || continue
    echo "   -> $(basename "$f")"
    psql "${PGRST_DB_URI}" -v ON_ERROR_STOP=1 -f "$f"
  done
fi

echo "==> Starting supervisor (gunicorn + postgrest)..."
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
