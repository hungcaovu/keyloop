"""
Timezone utility helpers.

All datetimes stored in DB are UTC (naive Python datetime objects at UTC).
Business-hour validation and lock-key derivation use the dealership's local timezone.
"""

from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo


BUSINESS_START = time(8, 0)   # 08:00 local
BUSINESS_END   = time(18, 0)  # 18:00 local


def to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC. If naive, assume it is already UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_dealership_local(utc_dt: datetime, timezone_str: str) -> datetime:
    """Convert a UTC datetime to the dealership's local timezone."""
    tz = ZoneInfo(timezone_str)
    aware = to_utc(utc_dt)
    return aware.astimezone(tz)


def local_booking_date(utc_dt: datetime, timezone_str: str) -> str:
    """Return the dealership-local calendar date (YYYY-MM-DD) for a UTC timestamp.

    Used for advisory lock key derivation (A13: lock scope is local date, not UTC date).
    """
    return to_dealership_local(utc_dt, timezone_str).date().isoformat()


def business_hours_utc(date, timezone_str: str):
    """Return (start_utc, end_utc) for the dealership's business hours on a given date.

    Args:
        date: a datetime.date or datetime.datetime (date portion used).
        timezone_str: IANA timezone string (e.g. "America/Chicago").

    Returns:
        Tuple[datetime, datetime]: UTC start and end of business hours.
    """
    tz = ZoneInfo(timezone_str)
    local_start = datetime.combine(date, BUSINESS_START).replace(tzinfo=tz)
    local_end   = datetime.combine(date, BUSINESS_END).replace(tzinfo=tz)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def validate_business_hours(window_start_utc: datetime, window_end_utc: datetime, timezone_str: str) -> bool:
    """Return True if the entire window fits within 08:00–18:00 dealership local time.

    Both datetimes are assumed UTC (naive = UTC, aware = converted to UTC first).
    """
    local_start = to_dealership_local(window_start_utc, timezone_str)
    local_end   = to_dealership_local(window_end_utc, timezone_str)
    return (
        local_start.time() >= BUSINESS_START
        and local_end.time() <= BUSINESS_END
        and local_start.date() == local_end.date()   # no cross-day appointments
    )


def strip_tzinfo(dt: datetime) -> datetime:
    """Return a naive datetime by discarding tzinfo (does NOT convert — assumes already UTC)."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def round_up_to_next_slot(dt: datetime, slot_minutes: int = 30) -> datetime:
    """Round a datetime UP to the next slot boundary (e.g. next 30-min mark).

    Works with both naive and aware datetimes. Returns naive UTC.
    """
    dt_naive = strip_tzinfo(dt)
    remainder = dt_naive.minute % slot_minutes
    if remainder == 0 and dt_naive.second == 0 and dt_naive.microsecond == 0:
        return dt_naive
    minutes_to_add = slot_minutes - remainder
    return dt_naive.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
