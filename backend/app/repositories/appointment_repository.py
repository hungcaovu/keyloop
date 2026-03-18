from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import text, func
from flask import current_app
from app.extensions import db
from app.models.appointment import Appointment, AppointmentStatus

PENDING_TTL_MINUTES = 10


def _active_hold_filter():
    """
    SQLAlchemy filter expression for appointments that currently block a slot:
      - CONFIRMED (no expiry)
      - PENDING where expires_at > NOW() (unexpired hold)

    EXPIRED, CANCELLED, COMPLETED rows are excluded — their resources are free.
    """
    return db.and_(
        Appointment.status.in_([
            AppointmentStatus.CONFIRMED.value,
            AppointmentStatus.PENDING.value,
        ]),
        db.or_(
            Appointment.expires_at.is_(None),
            Appointment.expires_at > func.now(),
        ),
    )


class AppointmentRepository:
    def get_by_id(self, appointment_id: str) -> Appointment | None:
        return db.session.get(Appointment, appointment_id)

    def load_booked_intervals(
        self, dealership_id: str, range_start: datetime, range_end: datetime
    ) -> tuple[dict, dict]:
        """
        Query 1 of the batch calendar load.

        Returns (tech_booked, bay_booked) — two separate dicts each mapping
        resource_id → [(scheduled_start, scheduled_end), ...].

        Kept in separate namespaces to avoid collisions when a technician and a
        service bay share the same integer primary key.
        """
        rows = db.session.execute(
            db.select(
                Appointment.technician_id,
                Appointment.service_bay_id,
                Appointment.scheduled_start,
                Appointment.scheduled_end,
            ).where(
                Appointment.dealership_id == dealership_id,
                _active_hold_filter(),
                # Overlap filter: NOT (end <= range_start OR start >= range_end)
                ~db.or_(
                    Appointment.scheduled_end <= range_start,
                    Appointment.scheduled_start >= range_end,
                ),
            )
        ).all()

        tech_booked: dict = {}
        bay_booked: dict = {}
        for tech_id, bay_id, start, end in rows:
            if tech_id:
                tech_booked.setdefault(tech_id, []).append((start, end))
            if bay_id:
                bay_booked.setdefault(bay_id, []).append((start, end))
        return tech_booked, bay_booked

    def get_recent_by_vehicle_ids(self, vehicle_ids: list, limit: int = 3) -> dict:
        """
        Batch-fetch the most recent non-cancelled appointments for each vehicle.

        Returns a dict mapping vehicle_id → [Appointment, ...] sorted by
        scheduled_start DESC, at most `limit` entries per vehicle.
        Uses ROW_NUMBER() so only one query is issued regardless of vehicle count.
        """
        if not vehicle_ids:
            return {}

        rn = (
            func.row_number()
            .over(
                partition_by=Appointment.vehicle_id,
                order_by=Appointment.scheduled_start.desc(),
            )
            .label("rn")
        )

        ranked_subq = (
            db.select(Appointment.id, rn)
            .where(
                Appointment.vehicle_id.in_(vehicle_ids),
                Appointment.status == AppointmentStatus.CONFIRMED.value,
            )
            .subquery()
        )

        rows = db.session.execute(
            db.select(Appointment)
            .join(ranked_subq, Appointment.id == ranked_subq.c.id)
            .where(ranked_subq.c.rn <= limit)
            .order_by(Appointment.vehicle_id, Appointment.scheduled_start.desc())
        ).scalars().all()

        result: dict = {}
        for appt in rows:
            result.setdefault(appt.vehicle_id, []).append(appt)
        return result

    def acquire_locks(
        self,
        technician_id: str,
        service_bay_id: str,
        scheduled_start: datetime,
        dealership_id: str,
    ) -> None:
        """
        Step 1 of atomic booking: acquire advisory locks BEFORE the re-check and INSERT.

        Advisory locks are skipped when SKIP_ADVISORY_LOCKS=True (test mode / SQLite).
        Must be called within an open transaction (Flask-SQLAlchemy ensures this).
        """
        if not current_app.config.get("SKIP_ADVISORY_LOCKS", False):
            self._acquire_advisory_locks(technician_id, service_bay_id, scheduled_start, dealership_id)

    def insert(
        self,
        customer_id: str,
        vehicle_id: str,
        dealership_id: str,
        service_type_id: str,
        technician_id: str,
        service_bay_id: str,
        scheduled_start: datetime,
        scheduled_end: datetime,
        notes: str | None = None,
        booked_by_customer_id: str | None = None,
    ) -> Appointment:
        """
        Step 2 of atomic booking: INSERT a PENDING hold after locks are held and
        re-check has passed.

        expires_at is set to now + PENDING_TTL_MINUTES. The advisor must call
        confirm() within the TTL to transition to CONFIRMED.
        """
        now_utc    = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now_utc + timedelta(minutes=PENDING_TTL_MINUTES)

        appointment = Appointment(
            customer_id=customer_id,
            booked_by_customer_id=booked_by_customer_id or customer_id,
            vehicle_id=vehicle_id,
            dealership_id=dealership_id,
            service_type_id=service_type_id,
            technician_id=technician_id,
            service_bay_id=service_bay_id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            notes=notes,
            status=AppointmentStatus.PENDING.value,
            expires_at=expires_at,
        )
        db.session.add(appointment)
        db.session.flush()
        return appointment

    def confirm(self, appointment: Appointment) -> Appointment:
        """Transition PENDING → CONFIRMED. Caller must validate expiry first."""
        appointment.status     = AppointmentStatus.CONFIRMED.value
        appointment.expires_at = None
        db.session.flush()
        return appointment

    def cancel(self, appointment: Appointment) -> Appointment:
        """Transition PENDING or CONFIRMED → CANCELLED."""
        appointment.status     = AppointmentStatus.CANCELLED.value
        appointment.expires_at = None
        db.session.flush()
        return appointment

    def _acquire_advisory_locks(
        self,
        technician_id: str,
        service_bay_id: str,
        scheduled_start: datetime,
        dealership_id: str,
    ) -> None:
        """
        Acquire PostgreSQL advisory locks scoped to (resource, local booking date).

        Lock scope = resource + local calendar date (not UTC date, not start time).
        - Two bookings with different start times on the SAME day can overlap.
        - Bookings on different days for the same resource CANNOT overlap.
        - booking_date is the dealership-local date (A13).

        Locks are acquired in sorted key order to prevent deadlocks.
        hashtext() is deterministic across all PG processes (unlike Python hash()).
        """
        from app.repositories.dealership_repository import DealershipRepository
        from app.utils.timezone import local_booking_date

        dealership = DealershipRepository().get_by_id(dealership_id)
        tz = dealership.timezone if dealership else "UTC"
        booking_date = local_booking_date(scheduled_start, tz)

        tech_key = f"tech:{technician_id}:{booking_date}"
        bay_key  = f"bay:{service_bay_id}:{booking_date}"

        for key in sorted([tech_key, bay_key]):
            db.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": key},
            )
