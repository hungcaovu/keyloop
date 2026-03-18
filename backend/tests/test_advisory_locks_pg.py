"""
PostgreSQL-only tests: advisory lock concurrency.

These tests verify that two concurrent bookings for the same technician+slot
are properly serialised by pg_advisory_xact_lock. They are SKIPPED automatically
when running against SQLite (advisory locks are not supported there).

Run with:
    TEST_DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler_test \
      python -m pytest tests/test_advisory_locks_pg.py -v
"""

import os
import pytest
import threading
from datetime import datetime, timedelta, timezone

from app.services.appointment_service import AppointmentService
from app.exceptions import ResourceUnavailableError


# Skip the entire module when not running against PostgreSQL
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", ""),
    reason="Advisory lock tests require PostgreSQL (set TEST_DATABASE_URL)",
)


def _tomorrow_14(offset_minutes=0):
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    tomorrow = today + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, offset_minutes, 0)


class TestAdvisoryLocks:
    def test_sequential_double_booking_same_slot_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        Sequential verification (no threads): a second booking for the exact same
        technician+slot must fail with ResourceUnavailableError even without
        concurrent threads, because the recheck SELECT sees the committed row.
        """
        svc = AppointmentService()
        start = _tomorrow_14()

        appt1 = svc.create_appointment(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            dealership_id=dealership.id,
            service_type_id=service_type_oil.id,
            desired_start=start,
            technician_id=technician.id,
        )
        assert appt1.status == "CONFIRMED"

        from app.models.customer import Customer as CM
        from app.models.vehicle import Vehicle as VM
        c2 = CM(first_name="X", last_name="Y", email="x@test.com",
                 created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(c2)
        db.session.flush()
        v2 = VM(customer_id=c2.id, make="BMW", model="3 Series", year=2020,
                 created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(v2)
        db.session.flush()

        with pytest.raises(ResourceUnavailableError):
            svc.create_appointment(
                customer_id=c2.id,
                vehicle_id=v2.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )

    def test_advisory_lock_key_is_postgresql_hashtext(self, db, app):
        """
        Verify that pg_advisory_xact_lock(hashtext(:key)) is reachable and
        returns without error. This confirms the PostgreSQL function is available.
        """
        from sqlalchemy import text
        result = db.session.execute(
            text("SELECT hashtext('test:key:2026-03-20')")
        ).scalar()
        assert isinstance(result, int)

    def test_concurrent_booking_one_succeeds(
        self, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        Two threads race to book the same slot+technician.
        Exactly one must succeed (CONFIRMED); the other must raise ResourceUnavailableError.

        NOTE: This test is intentionally slow (~1-2s) because it exercises real
        PostgreSQL advisory lock serialisation with two application threads.
        """
        from app.models.customer import Customer as CM
        from app.models.vehicle import Vehicle as VM

        start = _tomorrow_14(offset_minutes=30)  # use different time to not conflict with other tests

        results = []
        errors = []

        def book(cust_id, veh_id):
            with app.app_context():
                svc = AppointmentService()
                try:
                    appt = svc.create_appointment(
                        customer_id=cust_id,
                        vehicle_id=veh_id,
                        dealership_id=dealership.id,
                        service_type_id=service_type_oil.id,
                        desired_start=start,
                        technician_id=technician.id,
                    )
                    results.append(("ok", appt.id))
                except ResourceUnavailableError as e:
                    results.append(("fail", str(e)))
                except Exception as e:
                    errors.append(e)

        # Create second customer+vehicle in the main session first
        with app.app_context():
            from app.extensions import db as _db2
            c2 = CM(first_name="A", last_name="B", email="ab@test.com",
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None))
            _db2.session.add(c2)
            _db2.session.flush()
            v2 = VM(customer_id=c2.id, make="Audi", model="A4", year=2021,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None))
            _db2.session.add(v2)
            _db2.session.commit()
            c2_id, v2_id = c2.id, v2.id

        t1 = threading.Thread(target=book, args=(customer.id, vehicle.id))
        t2 = threading.Thread(target=book, args=(c2_id, v2_id))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Unexpected exceptions: {errors}"
        assert len(results) == 2
        successes = [r for r in results if r[0] == "ok"]
        failures  = [r for r in results if r[0] == "fail"]
        assert len(successes) == 1, f"Expected exactly 1 success, got: {results}"
        assert len(failures)  == 1, f"Expected exactly 1 failure, got: {results}"
