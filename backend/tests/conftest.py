"""
Shared test fixtures.

Supports two backends:

  SQLite (default, fast, no infra needed):
    python -m pytest

  PostgreSQL (real DB with advisory locks):
    TEST_DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler_test \
      python -m pytest --pg

SQLite uses create_all/drop_all per test (simple isolation).
PostgreSQL wraps each test in a SAVEPOINT-based transaction rollback so the
schema only needs to be created once (via `alembic upgrade head` before running).

IMPORTANT: Individual fixtures must NOT use `with app.app_context():` — the `db`
fixture already holds the context open. Nesting a second context causes Flask-SQLAlchemy
to call session.remove() on teardown, detaching all ORM objects.
"""

import os
import pytest
from datetime import datetime, timezone

from app import create_app
from app.extensions import db as _db
from app.config import TestingConfig


def pytest_addoption(parser):
    parser.addoption(
        "--pg",
        action="store_true",
        default=False,
        help="Run tests against PostgreSQL (requires TEST_DATABASE_URL env var)",
    )


def _using_postgres():
    return bool(os.getenv("TEST_DATABASE_URL", ""))


# ── App / DB fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Session-scoped app.
    - SQLite: creates all tables at session start, drops at end.
    - PostgreSQL: assumes schema already exists (run `alembic upgrade head` first).
    """
    application = create_app(TestingConfig)
    with application.app_context():
        if not _using_postgres():
            _db.create_all()
        yield application
        if not _using_postgres():
            _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """
    Function-scoped database isolation.
    - SQLite: each test gets its own in-memory DB (via the session-scoped `app`
      fixture — SQLite :memory: is connection-local, so every new connection starts
      fresh automatically).
    - PostgreSQL: wraps each test in a nested transaction (SAVEPOINT) and rolls
      back at the end, leaving the schema intact for the next test.
    """
    if _using_postgres():
        # Wrap every test in a SAVEPOINT so we can rollback after
        with app.app_context():
            connection = _db.engine.connect()
            transaction = connection.begin()
            # Bind the session to this connection so all test code shares it
            _db.session.configure(bind=connection)
            yield _db
            _db.session.remove()
            transaction.rollback()
            connection.close()
    else:
        # SQLite :memory: — the session-scoped app fixture owns the DB;
        # each function just resets the session state.
        with app.app_context():
            _db.session.begin_nested()   # SAVEPOINT (works in SQLite too)
            yield _db
            _db.session.rollback()
            _db.session.remove()
            # Re-create tables for next test (SQLite in-memory)
            _db.drop_all()
            _db.create_all()


@pytest.fixture(scope="function")
def client(app):
    """Flask test client — runs inside the active session app context."""
    return app.test_client()


# ── Domain object factories ────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def dealership(db):
    from app.models.dealership import Dealership
    d = Dealership(name="Test Dealership", city="Austin", state="TX", timezone="America/Chicago")
    db.session.add(d)
    db.session.commit()
    return d


@pytest.fixture
def service_type_oil(db):
    from app.models.service_type import ServiceType
    st = ServiceType(name="Oil Change", description="Quick oil change", duration_minutes=30, required_bay_type="GENERAL")
    db.session.add(st)
    db.session.commit()
    return st


@pytest.fixture
def service_type_brake(db):
    from app.models.service_type import ServiceType
    st = ServiceType(name="Brake Inspection", description="Full brake inspection", duration_minutes=90, required_bay_type="LIFT")
    db.session.add(st)
    db.session.commit()
    return st


@pytest.fixture
def technician(db, dealership, service_type_oil):
    from app.models.technician import Technician, TechnicianQualification
    tech = Technician(
        dealership_id=dealership.id,
        first_name="Carlos",
        last_name="Reyes",
        employee_number="T-001",
        is_active=True,
    )
    db.session.add(tech)
    db.session.flush()
    qual = TechnicianQualification(
        technician_id=tech.id,
        service_type_id=service_type_oil.id,
        certified_at=_now(),
    )
    db.session.add(qual)
    db.session.commit()
    return tech


@pytest.fixture
def technician_brake(db, dealership, service_type_brake):
    from app.models.technician import Technician, TechnicianQualification
    tech = Technician(
        dealership_id=dealership.id,
        first_name="Maria",
        last_name="Santos",
        employee_number="T-002",
        is_active=True,
    )
    db.session.add(tech)
    db.session.flush()
    qual = TechnicianQualification(
        technician_id=tech.id,
        service_type_id=service_type_brake.id,
        certified_at=_now(),
    )
    db.session.add(qual)
    db.session.commit()
    return tech


@pytest.fixture
def service_bay(db, dealership):
    from app.models.service_bay import ServiceBay
    bay = ServiceBay(dealership_id=dealership.id, bay_number="Bay 1", bay_type="GENERAL", is_active=True)
    db.session.add(bay)
    db.session.commit()
    return bay


@pytest.fixture
def service_bay_lift(db, dealership):
    from app.models.service_bay import ServiceBay
    bay = ServiceBay(dealership_id=dealership.id, bay_number="Bay 2", bay_type="LIFT", is_active=True)
    db.session.add(bay)
    db.session.commit()
    return bay


@pytest.fixture
def customer(db):
    from app.models.customer import Customer
    c = Customer(first_name="Jane", last_name="Smith", email="jane@test.com", phone="+1-555-0101", created_at=_now())
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def vehicle(db, customer):
    from app.models.vehicle import Vehicle
    v = Vehicle(customer_id=customer.id, vin="1HGCM82633A123456", make="Honda", model="Accord", year=2022, created_at=_now())
    db.session.add(v)
    db.session.commit()
    return v


@pytest.fixture
def vehicle_no_vin(db, customer):
    """Vehicle without VIN — gets auto-assigned vehicle_number via VehicleRepository.create()."""
    from app.services.vehicle_service import VehicleService
    svc = VehicleService()
    v = svc.create(customer_id=customer.id, make="Toyota", model="Camry", year=2020)
    return v
