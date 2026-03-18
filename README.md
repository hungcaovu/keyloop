# KeyLoop — Unified Service Scheduler

**Scenario A** of the Keyloop Technical Assessment.
A full-stack appointment booking system for automotive dealerships — replacing manual scheduling with real-time, concurrent-safe resource booking.

---

## What's Built

| Layer | Tech | Notes |
|-------|------|-------|
| **Backend API** | Python / Flask / SQLAlchemy 2 | REST API, 15+ endpoints |
| **Database** | PostgreSQL 15 | Advisory locks, Alembic migrations |
| **Frontend UI** | React + TypeScript + Vite | Full booking wizard, no mock |
| **Tests** | pytest | 3 000+ lines across unit, integration, and PG concurrency tests |
| **Containerisation** | Docker Compose | One command to run everything |
| **CI/CD** | GitHub Actions | Runs on every push and PR — full PostgreSQL test suite in Docker |

---

## Architecture Highlights

### 1. Dual-resource booking with PostgreSQL advisory locks

The hardest problem: two service advisors booking the same technician + bay at the same time.

```
POST /appointments (PENDING hold):
  ① Validate entities
  ② Check technician + bay are both free
  ③ Acquire pg_advisory_xact_lock (per resource × calendar date, sorted to prevent deadlock)
  ④ Re-check after lock (prevents TOCTOU race)
  ⑤ INSERT PENDING with expires_at = now + 10 min
  → 202 Accepted

PATCH /appointments/{id}/confirm (CONFIRMED):
  ① Validate hold not expired
  ② Transition PENDING → CONFIRMED, clear expires_at
  → 200 OK
```

PENDING holds with an expired `expires_at` are automatically excluded from availability queries — no background cleanup job required for correctness.

### 2. Calendar availability: 3 DB queries for 30 days

`GET /dealerships/{id}/availability` returns a full multi-day slot grid in exactly **3 queries**, regardless of date range or number of technicians/bays:

```
Q1: All booked intervals for the date range (one query, indexed overlap filter)
Q2: All qualified technicians for this service type
Q3: All compatible service bays (by bay_type)
→ In-memory slot generation at 30-min steps
```

Each slot reports `technician_count` and `bay_count` so the UI shows remaining capacity.

### 3. Efficient batch queries — no N+1

- **Top-3 recent appointments per vehicle** — single `ROW_NUMBER() OVER (PARTITION BY vehicle_id)` window query; zero extra queries per vehicle.
- **Vehicle list for customer** — `UNION` of owned vehicles + vehicles booked-on-behalf via a single query (supports the case where an advisor books a family member's car on behalf of a customer).
- **Booked intervals load** — one query covers all resources for the full calendar window.

### 4. Timezone-aware business hours

Each dealership stores its own IANA timezone (`America/Chicago`, `Europe/London`, etc.). Availability checks translate 08:00–18:00 **local** to UTC correctly, including DST transitions, so no slot bleeds across business-hours boundaries.

### 5. Vehicle identifier auto-detection

`GET /vehicles/{identifier}` routes to the correct lookup automatically:

| Pattern | Lookup |
|---------|--------|
| Numeric / `VH-000001` | Primary key (`vehicle.id`) |
| 17-char VIN `[A-HJ-NPR-Z0-9]` | `vehicle.vin` (unique) |
| `V-000042` | `vehicle.vehicle_number` (BigInt surrogate for VIN-less cars) |
| Anything else | `400 Bad Request` |

This covers the real operational gap: a car registered without a VIN (customer doesn't know it) is still bookable and findable via a short printed reference.

### 6. End-to-end request tracing (`X-Request-ID`)

The React client generates a unique `${timestamp_base36}-${random}` ID for every fetch and sends it as `X-Request-ID`. The backend injects it into every log record via a `logging.Filter` on Flask `g`, and echoes it in the response header. Every log line for a request is traceable back to the exact browser call.

### 7. Booked-on-behalf pattern

`Appointment` stores two separate customer references:
- `customer_id` — the vehicle owner (who the service is **for**)
- `booked_by_customer_id` — who made the booking (a spouse, fleet manager, etc.)

The UI surfaces this in the vehicle history view so advisors can see who requested each past service.

---

## Running Locally

### Prerequisites
- Docker + Docker Compose

### Option A — Full stack with Docker (recommended)

```bash
# Start PostgreSQL + backend + frontend in one command
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend (React) | http://localhost:3000 |
| Backend API | http://localhost:5001 |
| OpenAPI spec | http://localhost:5001/openapi.json |

The frontend nginx container proxies all `/api/*` calls to the Flask backend automatically — no CORS setup needed.

Seed the database with demo data (dealerships, technicians, service types):

```bash
docker compose --profile seed run --rm seeder
```

### Option B — Backend only with Docker

```bash
# Run only PostgreSQL + backend (no frontend)
docker compose up --build db backend
```

Backend runs on http://localhost:5001. Useful for API testing / Postman.

### Option C — Local development (no Docker)

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# With a local PostgreSQL:
export DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler_db
alembic upgrade head
flask seed-db       # optional demo data
gunicorn run:app --bind 0.0.0.0:5001 --workers 4

# Without PostgreSQL (SQLite — all features except advisory locks):
flask run --port 5001
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev        # starts at http://localhost:3000
# proxies /api/* → http://localhost:5001 (see vite.config.ts)
```

### Run tests

```bash
# Unit + integration tests (SQLite — fast, no Docker needed)
cd backend
pytest

# Unit + integration tests via Docker
docker compose --profile test run --rm test

# Full PostgreSQL tests (includes advisory lock concurrency tests)
docker compose --profile test-pg run --rm test-pg
```

### Manual concurrency booking test (flash script)

If you want a quick manual way to verify the race-condition guard (advisory locks + re-check),
use `backend/tools/flash_booking.py` to fire **N concurrent** `POST /appointments` requests
for the **same slot**.

Prereqs:
- Backend running at `http://localhost:5001`
- Seeded data (e.g. `docker compose --profile seed run --rm seeder`)

Run (auto-picks a valid future slot so you **don't need to set time manually**):

```bash
python backend/tools/flash_booking.py --n 10 \
  --dealership-id 1 --service-type-id 1  --technician-id 1\
  --customer-id C-000001 --vehicle-id VH-000001
```

Expected output shape:
- Exactly **1** request succeeds (typically `202 Accepted` with a `PENDING` hold)
- The remaining requests return **409** conflicts (slot taken by the concurrent winner)

Optional:
- Confirm the winning hold(s): add `--confirm`
- Pin a technician: add `--technician-id 1`
- Force a specific time: add `--desired-start "2026-04-01T14:00:00Z"`

---

## CI/CD Pipeline

Every push and pull request triggers the GitHub Actions workflow at [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

**What runs on each push/PR:**

```
1. Checkout code
2. Build Docker test image  (backend/Dockerfile — target: test)
3. Spin up PostgreSQL 15 service container
4. Run Alembic migrations against the live PostgreSQL instance
5. Run full pytest suite  (tests/ -v --tb=short)
   ├── Unit tests          (SQLite-compatible, fast)
   ├── Integration tests   (PostgreSQL — real schema, real queries)
   └── Concurrency tests   (advisory locks, race conditions)
```

**Branches covered:** all branches + all pull requests (`on: push: branches: ["**"]`).

**No PostgreSQL mock** — the CI pipeline always runs against a real PostgreSQL 15 container. This was a deliberate choice after finding that SQLite-compatible tests passed while a PostgreSQL migration was broken. Using the real database in CI catches schema drift, index differences, and advisory lock behaviour that mocks cannot replicate.

**Planned additions:**
- `ruff` / `flake8` lint check
- `mypy` type checking
- Frontend `tsc --noEmit` type check + `eslint`
- Test coverage report upload (Codecov)

---

## Test Coverage

| File | What's tested |
|------|--------------|
| `test_appointment_service.py` | Two-phase booking, conflict detection, hold expiry, cancel states, edge cases (800 lines) |
| `test_availability_service.py` | Slot generation with real Appointment objects — CONFIRMED/PENDING/CANCELLED/EXPIRED, 30/60/120-min durations, multi-technician scenarios (650 lines) |
| `test_advisory_locks_pg.py` | Actual concurrent threads racing on the same slot — verifies only one succeeds (PostgreSQL only) |
| `test_routes/` | HTTP integration tests for all endpoints |
| `test_customer_service.py`, `test_utils_*` | Service layer and utility unit tests |

---

## Project Structure

```
backend/
  app/
    models/          # SQLAlchemy models (7 tables)
    repositories/    # Data access layer
    services/        # Business logic (AppointmentService, AvailabilityService, ...)
    routes/          # Flask blueprints (REST endpoints)
    schemas/         # marshmallow request/response validation
    utils/           # Timezone helpers, entity ref formatting
  migrations/        # Alembic migration (single file — schema + check constraints)
  tests/             # 3 000+ lines, pytest

frontend/
  src/
    BookingWizard.tsx  # Multi-step booking UI (React)
    api.ts             # Typed API client with X-Request-ID
```

---

## Key Assumptions & Scope

These are the most important decisions that shape the entire design. Full rationale for all 23 assumptions is in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

| # | Assumption | Decision |
|---|-----------|----------|
| A1 | **User actor** | API is an **internal tool for Service Advisors** (dealership staff), not a customer self-service portal. |
| A2 | **Auth** | Out of scope for v1. JWT per dealership is the planned next step — adding it now would obscure the booking logic under assessment. |
| A3 | **Business hours** | 08:00–18:00 in the **dealership's local timezone**. The appointment must **finish** by 18:00, not just start. A 90-min service at 17:30 is rejected. |
| A5 | **Conflict response** | On `409`, the API always returns `next_available_slot` within 14 days — never a plain error with no guidance. |
| A7 | **Technician assignment** | Optional in the request. If provided, validated and pinned. If omitted, the **least-loaded qualified technician** is auto-assigned. |
| A12 | **Two-phase booking** | `POST /appointments` → `PENDING` (10-min hold). `PATCH /{id}/confirm` → `CONFIRMED`. The hold prevents the race condition between "see availability" and "submit booking". |
| A13 | **Timezones** | All timestamps stored in UTC. Business hours and lock scope use the **dealership's local calendar date** (e.g. `America/Chicago`), correctly handling DST. |
| A14 | **Phone uniqueness** | Not enforced — spouses/families share phones. Duplicate phone returns a `warning` alongside the new record; the advisor decides. |
| A15 | **VIN optional** | A vehicle can be booked without a VIN. VIN-less vehicles receive a `vehicle_number` surrogate (`V-000042`) for verbal/printed reference. Any customer can book any vehicle — ownership is not enforced at booking time. |
| A23 | **Soft hold TTL** | 10 minutes. Expired holds are **automatically excluded** from availability queries via `expires_at > NOW()` — no cleanup job needed for correctness. |

---

## Key Design Decisions

See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the full design document covering data model, concurrency strategy, observability, and AI collaboration narrative.

- **Why advisory locks over Redis**: no new infrastructure dependency; lock scope is resource × local calendar date, sorted key order prevents deadlock.
- **Why PENDING soft hold over immediate CONFIRM**: eliminates the TOCTOU window between availability check and INSERT without requiring `SERIALIZABLE` isolation on every read.
- **Why BigInteger PK over UUID**: 8-byte int indexes are significantly faster for high-volume slot queries; `VH-000001` display format preserves human-readability.
