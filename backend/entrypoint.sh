#!/bin/sh
set -e

echo "==> Waiting for PostgreSQL to be ready..."
until python - <<'EOF'
import psycopg2, os, sys
try:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
EOF
do
  echo "    PostgreSQL not ready yet, retrying in 2s..."
  sleep 2
done
echo "==> PostgreSQL is ready."

echo "==> Running Alembic migrations..."
alembic upgrade head
echo "==> Migrations complete."

if [ "${SEED_DB:-false}" = "true" ]; then
  echo "==> Seeding database..."
  flask seed-db
  echo "==> Seed complete."
fi

echo "==> Starting Gunicorn..."
exec gunicorn \
  --workers "${GUNICORN_WORKERS:-4}" \
  --bind "${GUNICORN_BIND:-0.0.0.0:5000}" \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  "run:app"
