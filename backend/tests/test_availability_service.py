"""
Unit tests for the core availability algorithm.

Tests the _overlaps() function, validate_business_hours(), and
round_up_to_next_slot() — the building blocks of the calendar view.
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
