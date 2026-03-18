# ── Stage 1: builder (install deps) ───────────────────────────────────────────
# Used by both runtime and test stages.
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 5000

# Entrypoint handles: wait for DB → migrate → (optionally seed) → start server
ENTRYPOINT ["sh", "entrypoint.sh"]

# ── Stage 3: test runner ────────────────────────────────────────────────────────
# Inherits all Python packages from builder.
# SQLite mode  : no Postgres needed, runs immediately.
# PostgreSQL mode: set TEST_DATABASE_URL; entrypoint.test.sh creates the DB +
#                  runs alembic before pytest.
FROM python:3.12-slim AS test

WORKDIR /app

# postgresql-client provides psql (needed to create scheduler_test DB in PG mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Reuse packages installed in builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source (code + tests + migrations)
COPY . .

# Default: run all tests against SQLite (fast, zero infrastructure)
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
