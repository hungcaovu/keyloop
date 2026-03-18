from __future__ import annotations
"""
AvailabilityService — Batch calendar and spot-check logic.

Calendar view (3 queries + in-memory):
  Q1: booked_intervals for the full date range
  Q2: qualified technicians (optionally filtered)
  Q3: compatible bays
  → in-memory slot generation, 0 additional DB calls

Spot check (2 fresh queries):
  Fresh queries needed — caller is confirming a specific slot; stale cache
  could hide a race condition between calendar view and POST /appointments.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from app.repositories.technician_repository import TechnicianRepository
from app.repositories.service_bay_repository import ServiceBayRepository
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.service_type_repository import ServiceTypeRepository
from app.repositories.dealership_repository import DealershipRepository
from app.models.technician import Technician
from app.exceptions import NotFoundError, NoAvailabilityError
from app.utils.timezone import validate_business_hours, round_up_to_next_slot

SLOT_STEP_MINUTES = 30
NEXT_SLOT_HORIZON_DAYS = 14
CALENDAR_MAX_DAYS = 30
BUSINESS_START_HOUR = 8
BUSINESS_END_HOUR = 18


@dataclass
class TimeSlot:
    start: datetime
    end: datetime
    technician_count: int


@dataclass
class DaySlots:
    date: str          # YYYY-MM-DD
    available_times: list[TimeSlot] = field(default_factory=list)


@dataclass
class CalendarResult:
    service_type_name: str
    duration_minutes: int
    from_date: str
    to_date: str
    filtered_technician: dict | None
    slots: list[DaySlots]


@dataclass
class SpotCheckResult:
    desired_start: datetime | None
    desired_end: datetime | None
    available: bool
    available_technicians: list
    bay_available: bool
    next_available_slot: datetime | None


def _overlaps(intervals: list, start: datetime, end: datetime) -> bool:
    """Return True if any existing interval overlaps [start, end)."""
    return any(
        not (existing_end <= start or existing_start >= end)
        for existing_start, existing_end in intervals
    )


class AvailabilityService:
    def __init__(self):
        self.tech_repo        = TechnicianRepository()
        self.bay_repo         = ServiceBayRepository()
        self.appt_repo        = AppointmentRepository()
        self.svc_type_repo    = ServiceTypeRepository()
        self.dealership_repo  = DealershipRepository()

    # ------------------------------------------------------------------
    # Calendar view (batch — 3 DB queries total)
    # ------------------------------------------------------------------

    def get_calendar_slots(
        self,
        dealership_id: str,
        service_type_id: str,
        from_date: date | None = None,
        days: int = 15,
        technician_id: str | None = None,
    ) -> CalendarResult:
        dealership   = self._get_dealership(dealership_id)
        service_type = self._get_service_type(service_type_id)

        logger.info(
            "availability.calendar.start",
            extra={
                "dealership_id": dealership_id,
                "service_type_id": service_type_id,
                "from_date": str(from_date),
                "days": days,
                "technician_id": technician_id,
            },
        )

        if technician_id:
            self._validate_technician(technician_id, dealership_id, service_type_id)

        tz       = ZoneInfo(dealership.timezone)
        now_utc  = datetime.now(timezone.utc).replace(tzinfo=None)
        duration = timedelta(minutes=service_type.duration_minutes)
        step     = timedelta(minutes=SLOT_STEP_MINUTES)

        # Determine range_start
        if from_date is None:
            from_date = now_utc.date()

        # A19: if from_date is today or past, start from now+1h rounded to next slot
        local_from_date = from_date
        range_start_utc = _local_day_start_utc(local_from_date, dealership.timezone)
        if range_start_utc <= now_utc:
            range_start_utc = round_up_to_next_slot(now_utc + timedelta(hours=1))

        to_date = from_date + timedelta(days=days)
        range_end_utc = _local_day_end_utc(to_date, dealership.timezone)

        # ── 3 queries ──────────────────────────────────────────────────────────
        booked   = self.appt_repo.load_booked_intervals(dealership_id, range_start_utc, range_end_utc)
        techs    = self.tech_repo.load_qualified(dealership_id, service_type_id, technician_id)
        bays     = self.bay_repo.load_compatible(dealership_id, service_type.required_bay_type)
        # ───────────────────────────────────────────────────────────────────────

        if not techs or not bays:
            logger.warning(
                "availability.calendar.no_resources",
                extra={"techs_count": len(techs), "bays_count": len(bays), "dealership_id": dealership_id},
            )
            # No qualified resources at all — return empty calendar
            return self._empty_calendar(service_type, from_date, to_date, technician_id, techs)

        # In-memory slot generation
        slots_by_date: dict[date, list[TimeSlot]] = defaultdict(list)
        cursor = range_start_utc

        while cursor < range_end_utc:
            window_end = cursor + duration

            # Business hours check (local time)
            if not validate_business_hours(cursor, window_end, dealership.timezone):
                # Skip to next day's business start if we've passed 18:00 local
                local_cursor = cursor.replace(tzinfo=timezone.utc).astimezone(tz)
                if local_cursor.hour >= BUSINESS_END_HOUR or local_cursor.hour < BUSINESS_START_HOUR:
                    next_day = (local_cursor.date() + timedelta(days=1))
                    cursor = _local_day_start_utc(next_day, dealership.timezone)
                    continue
                cursor += step
                continue

            tech_intervals = [booked.get(t.id, []) for t in techs]
            bay_intervals  = [booked.get(b.id, []) for b in bays]

            free_tech_count = sum(
                1 for intervals in tech_intervals
                if not _overlaps(intervals, cursor, window_end)
            )
            any_free_bay = any(
                not _overlaps(intervals, cursor, window_end)
                for intervals in bay_intervals
            )

            if free_tech_count > 0 and any_free_bay:
                local_date = cursor.replace(tzinfo=timezone.utc).astimezone(tz).date()
                slots_by_date[local_date].append(
                    TimeSlot(
                        start=cursor,       # UTC naive — matches what POST /appointments expects
                        end=window_end,     # UTC naive
                        technician_count=free_tech_count,
                    )
                )

            cursor += step

        # Build result grouped by day (include days with 0 slots as empty)
        all_days = []
        d = from_date
        while d < to_date:
            all_days.append(
                DaySlots(date=d.isoformat(), available_times=slots_by_date.get(d, []))
            )
            d += timedelta(days=1)

        filtered_tech_info = None
        if technician_id and techs:
            t = techs[0]
            filtered_tech_info = {"id": t.id, "name": t.full_name}

        return CalendarResult(
            service_type_name=service_type.name,
            duration_minutes=service_type.duration_minutes,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            filtered_technician=filtered_tech_info,
            slots=all_days,
        )

    # ------------------------------------------------------------------
    # Spot check (2 fresh queries)
    # ------------------------------------------------------------------

    def check_slot(
        self,
        dealership_id: str,
        service_type_id: str,
        desired_start: datetime,
        technician_id: str | None = None,
    ) -> SpotCheckResult:
        dealership   = self._get_dealership(dealership_id)
        service_type = self._get_service_type(service_type_id)
        window_end   = desired_start + timedelta(minutes=service_type.duration_minutes)

        # Business hours validation
        if not validate_business_hours(desired_start, window_end, dealership.timezone):
            return SpotCheckResult(
                desired_start=desired_start,
                desired_end=window_end,
                available=False,
                available_technicians=[],
                bay_available=False,
                next_available_slot=None,
            )

        # Fresh queries (not batch)
        techs  = self.tech_repo.find_available(
            dealership_id, service_type_id, desired_start, window_end, technician_id
        )
        bay_ok = self.bay_repo.count_available(
            dealership_id, service_type.required_bay_type, desired_start, window_end
        ) > 0

        available = bool(techs) and bay_ok

        next_slot = None
        if not available:
            try:
                next_slot = self.find_next_slot(dealership_id, service_type_id, desired_start)
            except NoAvailabilityError:
                next_slot = None

        logger.info(
            "availability.spot_check.result",
            extra={
                "dealership_id": dealership_id,
                "service_type_id": service_type_id,
                "desired_start": desired_start.isoformat(),
                "available": available,
                "bay_available": bay_ok,
                "available_technicians_count": len(techs),
            },
        )
        return SpotCheckResult(
            desired_start=desired_start,
            desired_end=window_end,
            available=available,
            available_technicians=techs,
            bay_available=bay_ok,
            next_available_slot=next_slot,
        )

    # ------------------------------------------------------------------
    # List qualified technicians (Step 0c.5)
    # ------------------------------------------------------------------

    def list_qualified_technicians(
        self, dealership_id: str, service_type_id: str
    ) -> list[Technician]:
        self._get_dealership(dealership_id)
        self._get_service_type(service_type_id)
        return self.tech_repo.list_qualified(dealership_id, service_type_id)

    # ------------------------------------------------------------------
    # Next slot finder (409 fallback)
    # ------------------------------------------------------------------

    def find_next_slot(
        self,
        dealership_id: str,
        service_type_id: str,
        from_time: datetime,
        horizon_days: int = NEXT_SLOT_HORIZON_DAYS,
    ) -> datetime:
        """
        Iterate forward from from_time in 30-min steps to find the first slot
        where both a qualified technician AND a compatible bay are free.
        Worst case: 14 × 20 slots × 2 queries = 560 queries.
        This path is only triggered on race-condition errors.
        """
        cursor = from_time + timedelta(minutes=SLOT_STEP_MINUTES)
        limit  = from_time + timedelta(days=horizon_days)

        dealership   = self._get_dealership(dealership_id)
        service_type = self._get_service_type(service_type_id)
        tz = ZoneInfo(dealership.timezone)

        while cursor < limit:
            window_end = cursor + timedelta(minutes=service_type.duration_minutes)

            if not validate_business_hours(cursor, window_end, dealership.timezone):
                local_cursor = cursor.replace(tzinfo=timezone.utc).astimezone(tz)
                if local_cursor.hour >= BUSINESS_END_HOUR:
                    next_day = local_cursor.date() + timedelta(days=1)
                    cursor = _local_day_start_utc(next_day, dealership.timezone)
                else:
                    cursor += timedelta(minutes=SLOT_STEP_MINUTES)
                continue

            techs  = self.tech_repo.find_available(
                dealership_id, service_type_id, cursor, window_end
            )
            bay_ok = self.bay_repo.count_available(
                dealership_id, service_type.required_bay_type, cursor, window_end
            ) > 0

            if techs and bay_ok:
                return cursor

            cursor += timedelta(minutes=SLOT_STEP_MINUTES)

        raise NoAvailabilityError(
            "No availability found within the 14-day search horizon. "
            "Please contact the dealership directly."
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_dealership(self, dealership_id: str):
        d = self.dealership_repo.get_by_id(dealership_id)
        if not d:
            raise NotFoundError(f"Dealership {dealership_id} not found.")
        return d

    def _get_service_type(self, service_type_id: str):
        st = self.svc_type_repo.get_by_id(service_type_id)
        if not st:
            raise NotFoundError(f"ServiceType {service_type_id} not found.")
        return st

    def _validate_technician(self, technician_id: str, dealership_id: str, service_type_id: str):
        techs = self.tech_repo.list_qualified(dealership_id, service_type_id, technician_id)
        if not techs:
            raise NotFoundError(
                f"Technician {technician_id} not found or not qualified for this service at this dealership."
            )

    def _empty_calendar(self, service_type, from_date: date, to_date: date, technician_id, techs) -> CalendarResult:
        all_days = []
        d = from_date
        while d < to_date:
            all_days.append(DaySlots(date=d.isoformat(), available_times=[]))
            d += timedelta(days=1)
        filtered_tech_info = None
        if technician_id and techs:
            t = techs[0]
            filtered_tech_info = {"id": t.id, "name": t.full_name}
        return CalendarResult(
            service_type_name=service_type.name,
            duration_minutes=service_type.duration_minutes,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            filtered_technician=filtered_tech_info,
            slots=all_days,
        )


# ---------------------------------------------------------------------------
# Helpers for local-time day boundaries
# ---------------------------------------------------------------------------

def _local_day_start_utc(d: date, timezone_str: str) -> datetime:
    from app.utils.timezone import business_hours_utc
    start, _ = business_hours_utc(d, timezone_str)
    return start


def _local_day_end_utc(d: date, timezone_str: str) -> datetime:
    from app.utils.timezone import business_hours_utc
    _, end = business_hours_utc(d, timezone_str)
    return end
