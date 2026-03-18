from __future__ import annotations
from datetime import datetime
from sqlalchemy import text
from flask import current_app
from app.extensions import db
from app.models.appointment import Appointment, AppointmentStatus


class AppointmentRepository:
    def get_by_id(self, appointment_id: str) -> Appointment | None:
        return db.session.get(Appointment, appointment_id)

    def load_booked_intervals(
        self, dealership_id: str, range_start: datetime, range_end: datetime
    ) -> dict:
        """
        Query 1 of the batch calendar load.

        Returns a dict mapping resource_id → [(scheduled_start, scheduled_end), ...].
        Uses the overlap filter (not a simple range filter) to correctly capture
        appointments that started before range_start but extend into the range.
        """
        rows = db.session.execute(
            db.select(
                Appointment.technician_id,
                Appointment.service_bay_id,
                Appointment.scheduled_start,
                Appointment.scheduled_end,
            ).where(
                Appointment.dealership_id == dealership_id,
                Appointment.status == AppointmentStatus.CONFIRMED.value,
                # Overlap filter: NOT (end <= range_start OR start >= range_end)
                ~db.or_(
                    Appointment.scheduled_end <= range_start,
                    Appointment.scheduled_start >= range_end,
                ),
            )
        ).all()

        result: dict = {}
        for tech_id, bay_id, start, end in rows:
            if tech_id:
                result.setdefault(tech_id, []).append((start, end))
            if bay_id:
                result.setdefault(bay_id, []).append((start, end))
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
        Step 2 of atomic booking: INSERT after locks are held and re-check has passed.

        Caller is responsible for calling acquire_locks() and validate_no_overlap()
        BEFORE calling this method. Do NOT flush here — caller commits the transaction.
        """
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
            status=AppointmentStatus.CONFIRMED.value,
        )
        db.session.add(appointment)
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
