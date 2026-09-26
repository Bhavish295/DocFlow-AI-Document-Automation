#!/bin/sh
set -e

# Ensure persistent storage directories exist and are writable by the app user.
# Named Docker volumes are often root-owned on first mount.
prepare_storage() {
  mkdir -p /app/storage/uploads /app/storage/anomaly_models /app/storage/models /app/storage/runtime
  if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /app/storage
  fi
}

run_migrations() {
  if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then
    echo "Skipping migrations (SKIP_MIGRATIONS=1)."
    return
  fi
  echo "Running database migrations (alembic upgrade head)..."
  if [ "$(id -u)" = "0" ]; then
    gosu appuser alembic upgrade head
  else
    alembic upgrade head
  fi
  echo "Migrations complete."
}

prepare_storage
run_migrations

# Drop privileges for the application process when started as root.
if [ "$(id -u)" = "0" ]; then
  exec gosu appuser "$@"
fi

exec "$@"
