#!/bin/sh
# entrypoint.test.sh — Bootstrap test database and run pytest (PostgreSQL mode).
#
# Used by docker-compose service `test-pg`.
# Expected env vars:
#   TEST_DATABASE_URL  — e.g. postgresql://scheduler:scheduler@db:5432/scheduler_test
#   PGHOST / PGUSER / PGPASSWORD — set automatically from compose environment
set -e

echo "[test] Waiting for PostgreSQL to be ready..."
until pg_isready -h "${PGHOST:-db}" -U "${PGUSER:-scheduler}" -q; do
  sleep 1
done
echo "[test] PostgreSQL is ready."

# Create test database if it doesn't exist yet
echo "[test] Creating scheduler_test database (if missing)..."
PGPASSWORD="${PGPASSWORD:-scheduler}" psql \
  -h "${PGHOST:-db}" \
  -U "${PGUSER:-scheduler}" \
  -d postgres \
  -tc "SELECT 1 FROM pg_database WHERE datname='scheduler_test'" \
  | grep -q 1 \
  || PGPASSWORD="${PGPASSWORD:-scheduler}" psql \
       -h "${PGHOST:-db}" \
       -U "${PGUSER:-scheduler}" \
       -d postgres \
       -c "CREATE DATABASE scheduler_test;"

echo "[test] Running Alembic migrations on scheduler_test..."
DATABASE_URL="${TEST_DATABASE_URL}" alembic upgrade head

echo "[test] Starting pytest..."
exec python -m pytest tests/ -v --tb=short -s --log-cli-level=INFO "$@"
