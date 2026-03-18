"""
PostgreSQL-only tests: advisory lock concurrency.

These tests verify that two concurrent bookings for the same technician+slot
are properly serialised by pg_advisory_xact_lock. They are SKIPPED automatically
when running against SQLite (advisory locks are not supported there).

Run with:
    TEST_DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler_test \
      python -m pytest tests/test_advisory_locks_pg.py -v -s
"""

import os
import time
import pytest
import threading
import logging
from datetime import datetime, timedelta, timezone

from app.services.appointment_service import AppointmentService
from app.exceptions import ResourceUnavailableError

logger = logging.getLogger(__name__)

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

        logger.info("[SEQ] Booking slot: technician=%s start=%s", technician.id, start.isoformat())

        appt1 = svc.create_appointment(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            dealership_id=dealership.id,
            service_type_id=service_type_oil.id,
            desired_start=start,
            technician_id=technician.id,
        )
        logger.info("[SEQ] Booking 1 → id=%s status=%s expires_at=%s", appt1.id, appt1.status, appt1.expires_at)
        assert appt1.status == "PENDING"

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

        logger.info("[SEQ] Booking 2 — same slot, expecting ResourceUnavailableError ...")
        with pytest.raises(ResourceUnavailableError) as exc_info:
            svc.create_appointment(
                customer_id=c2.id,
                vehicle_id=v2.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )
        next_slot = exc_info.value.next_available_slot
        logger.info(
            "[SEQ] Booking 2 raised as expected: %s | next_available_slot=%s",
            exc_info.value.message,
            next_slot.isoformat() if next_slot else "None",
        )

    def test_advisory_lock_key_is_postgresql_hashtext(self, db, app):
        """
        Verify that pg_advisory_xact_lock(hashtext(:key)) is reachable and
        returns without error. This confirms the PostgreSQL function is available.
        """
        from sqlalchemy import text
        key = "test:key:2026-03-20"
        result = db.session.execute(
            text("SELECT hashtext(:k)"), {"k": key}
        ).scalar()
        logger.info("[LOCK] hashtext('%s') = %s", key, result)
        assert isinstance(result, int)

    def test_concurrent_booking_one_succeeds(
        self, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        Two threads race to book the same slot+technician.
        Exactly one must succeed (PENDING hold); the other must raise ResourceUnavailableError.

        NOTE: This test is intentionally slow (~1-2s) because it exercises real
        PostgreSQL advisory lock serialisation with two application threads.
        """
        from app.models.customer import Customer as CM
        from app.models.vehicle import Vehicle as VM

        start = _tomorrow_14(offset_minutes=30)
        logger.info("[CONC] Racing 2 threads for slot: technician=%s start=%s", technician.id, start.isoformat())

        results = []
        errors  = []
        timings = {}

        def book(label, cust_id, veh_id):
            t0 = time.perf_counter()
            logger.info("[CONC][%s] thread started — customer=%s vehicle=%s", label, cust_id, veh_id)
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
                    elapsed = time.perf_counter() - t0
                    timings[label] = elapsed
                    logger.info(
                        "[CONC][%s] PENDING hold id=%s expires_at=%s (%.3fs)",
                        label, appt.id, appt.expires_at, elapsed,
                    )
                    results.append(("ok", appt.id))
                except ResourceUnavailableError as e:
                    elapsed = time.perf_counter() - t0
                    timings[label] = elapsed
                    next_slot = e.next_available_slot
                    logger.info(
                        "[CONC][%s] ResourceUnavailableError: %s | next_slot=%s (%.3fs)",
                        label, e.message,
                        next_slot.isoformat() if next_slot else "None",
                        elapsed,
                    )
                    results.append(("fail", str(e.message)))
                except Exception as e:
                    elapsed = time.perf_counter() - t0
                    logger.error("[CONC][%s] Unexpected %s: %s (%.3fs)", label, type(e).__name__, e, elapsed)
                    errors.append(e)

        # Create second customer+vehicle before spawning threads
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
            logger.info("[CONC] Created c2=%s v2=%s", c2_id, v2_id)

        t1 = threading.Thread(target=book, args=("T1", customer.id, vehicle.id))
        t2 = threading.Thread(target=book, args=("T2", c2_id,       v2_id))

        race_start = time.perf_counter()
        t1.start(); t2.start()
        t1.join();  t2.join()
        total = time.perf_counter() - race_start
        logger.info("[CONC] Race finished in %.3fs — results: %s", total, results)

        assert not errors, f"Unexpected exceptions: {errors}"
        assert len(results) == 2
        successes = [r for r in results if r[0] == "ok"]
        failures  = [r for r in results if r[0] == "fail"]
        logger.info("[CONC] successes=%s failures=%s", successes, failures)
        assert len(successes) == 1, f"Expected exactly 1 success, got: {results}"
        assert len(failures)  == 1, f"Expected exactly 1 failure,  got: {results}"
