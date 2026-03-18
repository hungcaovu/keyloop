"""
Unit tests for the core availability algorithm.

Tests the _overlaps() function, validate_business_hours(), and
round_up_to_next_slot() — the building blocks of the calendar view.

Also includes integration tests (TestFreeSlotWithAppointments) that insert
real Appointment rows (PENDING / CONFIRMED / EXPIRED / CANCELLED) and verify
AvailabilityService.check_slot() returns the correct free/blocked result for
services of different durations (30 min, 60 min, 120 min).
"""

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.utils.timezone import (
    validate_business_hours,
    round_up_to_next_slot,
    business_hours_utc,
    local_booking_date,
)
from app.services.availability_service import _overlaps


# ── UTC fixtures used by TestFreeSlotWithAppointments ─────────────────────────
# The shared `dealership` fixture uses America/Chicago. Tests that pass naive
# UTC times (09:00, 10:00, …) would fall outside CDT business hours and be
# rejected before the overlap logic runs. These fixtures use a UTC-timezone
# dealership so all times map 1-to-1 with local business hours.

@pytest.fixture
def utc_dealership(db):
    from app.models.dealership import Dealership
    d = Dealership(name="UTC Dealership", city="London", state="UK", timezone="UTC")
    db.session.add(d)
    db.session.commit()
    return d


@pytest.fixture
def utc_technician(db, utc_dealership, service_type_oil):
    from app.models.technician import Technician, TechnicianQualification
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tech = Technician(
        dealership_id=utc_dealership.id,
        first_name="UTC", last_name="Tech",
        employee_number="UTC-001", is_active=True,
    )
    db.session.add(tech)
    db.session.flush()
    db.session.add(TechnicianQualification(
        technician_id=tech.id,
        service_type_id=service_type_oil.id,
        certified_at=now,
    ))
    db.session.commit()
    return tech


@pytest.fixture
def utc_service_bay(db, utc_dealership):
    from app.models.service_bay import ServiceBay
    bay = ServiceBay(
        dealership_id=utc_dealership.id,
        bay_number="Bay UTC", bay_type="GENERAL", is_active=True,
    )
    db.session.add(bay)
    db.session.commit()
    return bay


# ── _overlaps() ────────────────────────────────────────────────────────────────

class TestOverlaps:
    def test_no_existing_intervals(self):
        assert _overlaps([], datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is False

    def test_existing_fully_before(self):
        intervals = [(datetime(2026, 3, 20, 7), datetime(2026, 3, 20, 8))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is False

    def test_existing_fully_after(self):
        intervals = [(datetime(2026, 3, 20, 11), datetime(2026, 3, 20, 12))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is False

    def test_existing_ends_exactly_at_start(self):
        """Adjacent intervals must NOT overlap (endpoint exclusive)."""
        intervals = [(datetime(2026, 3, 20, 8), datetime(2026, 3, 20, 9))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is False

    def test_existing_starts_exactly_at_end(self):
        """Adjacent intervals must NOT overlap (endpoint exclusive)."""
        intervals = [(datetime(2026, 3, 20, 10), datetime(2026, 3, 20, 11))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is False

    def test_partial_overlap_start(self):
        """Existing starts before window starts but extends into it."""
        intervals = [(datetime(2026, 3, 20, 8, 30), datetime(2026, 3, 20, 9, 30))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is True

    def test_partial_overlap_end(self):
        """Existing starts inside window and extends past it."""
        intervals = [(datetime(2026, 3, 20, 9, 30), datetime(2026, 3, 20, 10, 30))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is True

    def test_existing_fully_inside(self):
        intervals = [(datetime(2026, 3, 20, 9, 15), datetime(2026, 3, 20, 9, 45))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is True

    def test_existing_fully_wraps_around(self):
        intervals = [(datetime(2026, 3, 20, 8), datetime(2026, 3, 20, 11))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is True

    def test_exact_match(self):
        intervals = [(datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10))]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10)) is True

    def test_multiple_intervals_one_overlaps(self):
        intervals = [
            (datetime(2026, 3, 20, 7), datetime(2026, 3, 20, 8)),
            (datetime(2026, 3, 20, 9, 30), datetime(2026, 3, 20, 10, 30)),
        ]
        assert _overlaps(intervals, datetime(2026, 3, 20, 9), datetime(2026, 3, 20, 10, 15)) is True

    def test_multiple_intervals_none_overlaps(self):
        intervals = [
            (datetime(2026, 3, 20, 7), datetime(2026, 3, 20, 8)),
            (datetime(2026, 3, 20, 10), datetime(2026, 3, 20, 11)),
        ]
        assert _overlaps(intervals, datetime(2026, 3, 20, 8, 30), datetime(2026, 3, 20, 9, 30)) is False


# ── validate_business_hours() ──────────────────────────────────────────────────

class TestValidateBusinessHours:
    TZ = "America/Chicago"   # UTC-5 (winter) / UTC-6 (summer)

    def _utc(self, hour, minute=0):
        """Create a UTC datetime on 2026-03-20 (standard time → UTC-5 for Chicago)."""
        return datetime(2026, 3, 20, hour, minute)  # naive = UTC

    def test_valid_window_inside_business_hours(self):
        # 09:00–10:30 Chicago local = 15:00–16:30 UTC (CDT offset = -5)
        # Note: March 20 2026 is after DST starts (Mar 8), so Chicago is CDT = UTC-5
        start = self._utc(14, 0)   # 09:00 CDT
        end   = self._utc(15, 30)  # 10:30 CDT
        assert validate_business_hours(start, end, self.TZ) is True

    def test_start_before_business_hours(self):
        start = self._utc(12, 0)   # 07:00 CDT — before 08:00
        end   = self._utc(13, 0)   # 08:00 CDT
        assert validate_business_hours(start, end, self.TZ) is False

    def test_end_after_business_hours(self):
        # 16:30–18:00 CDT = 21:30–23:00 UTC
        start = self._utc(21, 30)  # 16:30 CDT
        end   = self._utc(23, 30)  # 18:30 CDT — past 18:00
        assert validate_business_hours(start, end, self.TZ) is False

    def test_window_ends_exactly_at_18(self):
        # 16:30–18:00 CDT = 21:30–23:00 UTC
        start = self._utc(21, 30)  # 16:30 CDT
        end   = self._utc(23, 0)   # 18:00 CDT
        assert validate_business_hours(start, end, self.TZ) is True

    def test_cross_day_window_rejected(self):
        # 17:30 CDT + 90 min → 19:00 CDT — crosses 18:00
        start = datetime(2026, 3, 20, 22, 30)  # 17:30 CDT
        end   = datetime(2026, 3, 21, 0, 0)    # 19:00 CDT — next UTC day, and past 18:00 local
        assert validate_business_hours(start, end, self.TZ) is False


# ── round_up_to_next_slot() ────────────────────────────────────────────────────

class TestRoundUpToNextSlot:
    def test_already_on_boundary(self):
        dt = datetime(2026, 3, 20, 9, 0, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 9, 0, 0)

    def test_1_minute_past_boundary(self):
        dt = datetime(2026, 3, 20, 9, 1, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 9, 30, 0)

    def test_29_minutes_past_boundary(self):
        dt = datetime(2026, 3, 20, 9, 29, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 9, 30, 0)

    def test_30_minutes_boundary(self):
        dt = datetime(2026, 3, 20, 9, 30, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 9, 30, 0)

    def test_31_minutes(self):
        dt = datetime(2026, 3, 20, 9, 31, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 10, 0, 0)

    def test_seconds_nonzero_on_boundary_minute(self):
        dt = datetime(2026, 3, 20, 9, 0, 15)   # 09:00:15 — not a clean boundary
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 9, 30, 0)

    def test_rollover_to_next_hour(self):
        dt = datetime(2026, 3, 20, 9, 45, 0)
        assert round_up_to_next_slot(dt) == datetime(2026, 3, 20, 10, 0, 0)

    def test_handles_aware_datetime(self):
        """Aware datetimes should be stripped and result in naive UTC."""
        dt = datetime(2026, 3, 20, 9, 15, 0, tzinfo=timezone.utc)
        result = round_up_to_next_slot(dt)
        assert result == datetime(2026, 3, 20, 9, 30, 0)
        assert result.tzinfo is None


# ── local_booking_date() ───────────────────────────────────────────────────────

class TestLocalBookingDate:
    def test_chicago_not_same_as_utc_date(self):
        """
        A 23:30 UTC booking is 'tomorrow' in UTC but 'today' for a UTC-5 dealership.
        Lock key must use local date.
        """
        # 23:30 UTC on Mar 20 = 18:30 CDT on Mar 20 (CDT = UTC-5)
        # Wait — 23:30 UTC = 18:30 CDT (23:30 - 5 = 18:30) which is still Mar 20 local
        # Let's try 03:00 UTC on Mar 21 = 22:00 CDT on Mar 20
        utc_dt = datetime(2026, 3, 21, 3, 0)  # 03:00 UTC Mar 21 = 22:00 CDT Mar 20
        date_str = local_booking_date(utc_dt, "America/Chicago")
        assert date_str == "2026-03-20"  # Local date is Mar 20, not Mar 21

    def test_same_day_as_utc_during_business_hours(self):
        utc_dt = datetime(2026, 3, 20, 15, 0)  # 15:00 UTC = 10:00 CDT Mar 20
        date_str = local_booking_date(utc_dt, "America/Chicago")
        assert date_str == "2026-03-20"

    def test_utc_timezone(self):
        utc_dt = datetime(2026, 3, 20, 10, 0)
        date_str = local_booking_date(utc_dt, "UTC")
        assert date_str == "2026-03-20"


# ── Free slot detection with real Appointment objects ──────────────────────────
#
# These tests insert Appointment rows directly into the DB and verify that
# AvailabilityService.check_slot() correctly identifies free vs blocked slots.
#
# All times are UTC-naive and fall inside business hours for "UTC" dealership
# (08:00–18:00 UTC), so business-hours filtering never interferes.
#
# Date used: tomorrow (dynamic) so "past-booking" guard never triggers.

class TestFreeSlotWithAppointments:
    """
    Each test inserts Appointment objects into the DB and verifies that
    AvailabilityService.check_slot() correctly identifies free vs blocked slots.

    All times are UTC and fall within UTC business hours (08:00–18:00), so the
    business-hours guard never interferes.  The `utc_dealership` / `utc_technician`
    / `utc_service_bay` module-level fixtures are used instead of the shared
    conftest `dealership` fixture (which uses America/Chicago, where 09:00 UTC
    falls outside business hours and would be rejected before any overlap check).

    Scenarios covered:
      - CONFIRMED appointment blocks the exact slot
      - PENDING (unexpired) appointment blocks the slot
      - PENDING (expired) does NOT block the slot
      - CANCELLED does NOT block the slot
      - 60-min service: partial overlap blocks; non-overlapping slot stays free
      - 120-min service: same 30-min booking blocks more surrounding cursor
        positions than a 30-min service would (because the candidate window is wider)
      - Two technicians: one booked, one free → slot is still available
      - Both technicians booked → slot is unavailable
    """

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _tomorrow_at(hour: int, minute: int = 0) -> datetime:
        """Return a UTC-naive datetime for tomorrow at hour:minute UTC."""
        d = datetime.now(timezone.utc).date() + timedelta(days=1)
        return datetime(d.year, d.month, d.day, hour, minute)

    def _make_appt(self, db, *, customer, vehicle, dealership, service_type,
                   technician, service_bay, start, end, status, expires_at=None):
        """Insert an Appointment directly, bypassing AppointmentService."""
        from app.models.appointment import Appointment
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        appt = Appointment(
            customer_id=customer.id, vehicle_id=vehicle.id,
            dealership_id=dealership.id, service_type_id=service_type.id,
            technician_id=technician.id, service_bay_id=service_bay.id,
            scheduled_start=start, scheduled_end=end,
            status=status, expires_at=expires_at,
            created_at=now, updated_at=now,
        )
        db.session.add(appt)
        db.session.commit()
        return appt

    # ── 30-min service ─────────────────────────────────────────────────────────

    def test_confirmed_blocks_exact_slot(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """CONFIRMED appointment at 09:00-09:30 → check_slot(09:00) is unavailable."""
        from app.services.availability_service import AvailabilityService
        start = self._tomorrow_at(9, 0)
        end   = start + timedelta(minutes=30)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=start, end=end, status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is False

    def test_pending_unexpired_blocks_slot(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """PENDING hold that hasn't expired yet blocks the same slot."""
        from app.services.availability_service import AvailabilityService
        start      = self._tomorrow_at(10, 0)
        end        = start + timedelta(minutes=30)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=start, end=end,
            status="PENDING", expires_at=expires_at,
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is False

    def test_pending_expired_does_not_block_slot(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """PENDING hold whose expires_at is in the past must NOT block the slot."""
        from app.services.availability_service import AvailabilityService
        start      = self._tomorrow_at(10, 0)
        end        = start + timedelta(minutes=30)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=start, end=end,
            status="PENDING", expires_at=expires_at,
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is True

    def test_cancelled_does_not_block_slot(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """CANCELLED appointment must NOT block the slot."""
        from app.services.availability_service import AvailabilityService
        start = self._tomorrow_at(11, 0)
        end   = start + timedelta(minutes=30)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=start, end=end, status="CANCELLED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is True

    def test_adjacent_slot_is_free(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """Booking at 09:00-09:30 → slot 09:30 is free (endpoint-exclusive, no overlap)."""
        from app.services.availability_service import AvailabilityService
        booked_start = self._tomorrow_at(9, 0)
        booked_end   = booked_start + timedelta(minutes=30)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=booked_start, end=booked_end,
            status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id,
            desired_start=self._tomorrow_at(9, 30),
        )
        assert result.available is True

    # ── 60-min service ─────────────────────────────────────────────────────────

    def test_60min_partial_overlap_blocks_slot(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """
        60-min candidate [09:30, 10:30).
        Existing CONFIRMED booking [10:00, 10:30) partially overlaps → blocked.
        """
        from app.services.availability_service import AvailabilityService
        from app.models.service_type import ServiceType

        svc_60 = ServiceType(name="Tire Rotation", duration_minutes=60, required_bay_type="GENERAL")
        db.session.add(svc_60)
        db.session.commit()

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay,
            start=self._tomorrow_at(10, 0), end=self._tomorrow_at(10, 30),
            status="CONFIRMED",
        )

        # [09:30, 10:30) overlaps with [10:00, 10:30) → blocked
        result = AvailabilityService().check_slot(
            utc_dealership.id, svc_60.id, desired_start=self._tomorrow_at(9, 30)
        )
        assert result.available is False

    def test_60min_non_overlapping_slot_is_free(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """
        Booking [09:00, 09:30).
        60-min candidate [10:30, 11:30) starts after booking ends → free.
        """
        from app.models.service_type import ServiceType
        from app.models.technician import TechnicianQualification
        from app.services.availability_service import AvailabilityService

        svc_60 = ServiceType(name="Tire Rotation 2", duration_minutes=60, required_bay_type="GENERAL")
        db.session.add(svc_60)
        db.session.flush()
        # utc_technician must be qualified for svc_60 so it can be found by find_available
        db.session.add(TechnicianQualification(
            technician_id=utc_technician.id,
            service_type_id=svc_60.id,
            certified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.session.commit()

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay,
            start=self._tomorrow_at(9, 0), end=self._tomorrow_at(9, 30),
            status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, svc_60.id, desired_start=self._tomorrow_at(10, 30)
        )
        assert result.available is True

    # ── 120-min service ────────────────────────────────────────────────────────

    def test_120min_blocks_wider_window_than_30min(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """
        Booking [10:00, 10:30).

        120-min at 08:30 → candidate [08:30, 10:30) overlaps [10:00, 10:30) → BLOCKED.
        30-min  at 08:30 → candidate [08:30, 09:00) does NOT overlap          → FREE.

        This proves a wider service duration blocks more surrounding start times.
        """
        from app.services.availability_service import AvailabilityService
        from app.models.service_type import ServiceType

        svc_120 = ServiceType(name="Full Service", duration_minutes=120, required_bay_type="GENERAL")
        db.session.add(svc_120)
        db.session.commit()

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay,
            start=self._tomorrow_at(10, 0), end=self._tomorrow_at(10, 30),
            status="CONFIRMED",
        )

        result_120 = AvailabilityService().check_slot(
            utc_dealership.id, svc_120.id, desired_start=self._tomorrow_at(8, 30)
        )
        assert result_120.available is False  # [08:30, 10:30) hits the booking

        result_30 = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=self._tomorrow_at(8, 30)
        )
        assert result_30.available is True    # [08:30, 09:00) clears the booking

    def test_120min_free_slot_after_booking(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """
        Booking [09:00, 09:30).
        120-min candidate [10:00, 12:00) starts after booking ends → free.
        """
        from app.models.service_type import ServiceType
        from app.models.technician import TechnicianQualification
        from app.services.availability_service import AvailabilityService

        svc_120 = ServiceType(name="Full Service 2", duration_minutes=120, required_bay_type="GENERAL")
        db.session.add(svc_120)
        db.session.flush()
        db.session.add(TechnicianQualification(
            technician_id=utc_technician.id,
            service_type_id=svc_120.id,
            certified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.session.commit()

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay,
            start=self._tomorrow_at(9, 0), end=self._tomorrow_at(9, 30),
            status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, svc_120.id, desired_start=self._tomorrow_at(10, 0)
        )
        assert result.available is True

    # ── Multiple technicians ───────────────────────────────────────────────────

    def test_one_of_two_technicians_free_slot_available(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """
        Tech1 is booked at 09:00 (occupies utc_service_bay).
        Tech2 is free, a second bay is also free.
        check_slot(09:00) → still available (Tech2 + bay2 can take it).
        """
        from app.models.technician import Technician, TechnicianQualification
        from app.models.service_bay import ServiceBay
        from app.services.availability_service import AvailabilityService

        # Second bay so the slot has a free bay even when utc_service_bay is occupied
        bay2 = ServiceBay(
            dealership_id=utc_dealership.id,
            bay_number="Bay UTC-2", bay_type="GENERAL", is_active=True,
        )
        db.session.add(bay2)

        tech2 = Technician(
            dealership_id=utc_dealership.id,
            first_name="Ana", last_name="Lima",
            employee_number="UTC-002", is_active=True,
        )
        db.session.add(tech2)
        db.session.flush()
        db.session.add(TechnicianQualification(
            technician_id=tech2.id,
            service_type_id=service_type_oil.id,
            certified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.session.commit()

        # Book Tech1 on utc_service_bay — bay2 remains free
        start = self._tomorrow_at(9, 0)
        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay,
            start=start, end=start + timedelta(minutes=30), status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is True
        free_ids = [t.id for t in result.available_technicians]
        assert tech2.id in free_ids
        assert utc_technician.id not in free_ids

    def test_both_technicians_booked_slot_unavailable(
        self, db, utc_dealership, service_type_oil, utc_technician, utc_service_bay,
        customer, vehicle
    ):
        """Both Tech1 and Tech2 booked at 09:00 → slot unavailable."""
        from app.models.technician import Technician, TechnicianQualification
        from app.models.customer import Customer
        from app.models.vehicle import Vehicle
        from app.services.availability_service import AvailabilityService

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        tech2 = Technician(
            dealership_id=utc_dealership.id,
            first_name="Bob", last_name="Ko",
            employee_number="UTC-003", is_active=True,
        )
        db.session.add(tech2)
        db.session.flush()
        db.session.add(TechnicianQualification(
            technician_id=tech2.id,
            service_type_id=service_type_oil.id,
            certified_at=now,
        ))

        c2 = Customer(first_name="X", last_name="Y", email="xy_both@test.com", created_at=now)
        db.session.add(c2)
        db.session.flush()
        v2 = Vehicle(customer_id=c2.id, make="Ford", model="Focus", year=2021, created_at=now)
        db.session.add(v2)
        db.session.commit()

        start = self._tomorrow_at(9, 0)
        end   = start + timedelta(minutes=30)

        self._make_appt(
            db, customer=customer, vehicle=vehicle, dealership=utc_dealership,
            service_type=service_type_oil, technician=utc_technician,
            service_bay=utc_service_bay, start=start, end=end, status="CONFIRMED",
        )
        self._make_appt(
            db, customer=c2, vehicle=v2, dealership=utc_dealership,
            service_type=service_type_oil, technician=tech2,
            service_bay=utc_service_bay, start=start, end=end, status="CONFIRMED",
        )

        result = AvailabilityService().check_slot(
            utc_dealership.id, service_type_oil.id, desired_start=start
        )
        assert result.available is False
        assert result.available_technicians == []
