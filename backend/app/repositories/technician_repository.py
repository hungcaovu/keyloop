from __future__ import annotations
from datetime import datetime
from sqlalchemy import text, func
from app.extensions import db
from app.models.technician import Technician, TechnicianQualification
from app.models.appointment import Appointment, AppointmentStatus
from app.repositories.appointment_repository import _active_hold_filter


class TechnicianRepository:
    # ------------------------------------------------------------------
    # Listing / lookup
    # ------------------------------------------------------------------

    def get_by_id(self, technician_id: str) -> Technician | None:
        return db.session.get(Technician, technician_id)

    def list_qualified(
        self,
        dealership_id: str,
        service_type_id: str,
        technician_id: str | None = None,
    ) -> list[Technician]:
        """List active technicians qualified for a service type, optionally filtered to one."""
        stmt = (
            db.select(Technician)
            .join(
                TechnicianQualification,
                db.and_(
                    TechnicianQualification.technician_id == Technician.id,
                    TechnicianQualification.service_type_id == service_type_id,
                ),
            )
            .where(
                Technician.dealership_id == dealership_id,
                Technician.is_active == True,
            )
        )
        if technician_id:
            stmt = stmt.where(Technician.id == technician_id)
        stmt = stmt.order_by(Technician.last_name, Technician.first_name)
        return list(db.session.execute(stmt).unique().scalars().all())

    # ------------------------------------------------------------------
    # Availability (fresh queries — spot check & booking)
    # ------------------------------------------------------------------

    def find_available(
        self,
        dealership_id: str,
        service_type_id: str,
        window_start: datetime,
        window_end: datetime,
        technician_id: str | None = None,
    ) -> list[Technician]:
        """
        Return qualified technicians with NO overlapping active appointment
        (CONFIRMED or unexpired PENDING hold).
        """
        overlap_subq = (
            db.select(Appointment.id)
            .where(
                Appointment.technician_id == Technician.id,
                _active_hold_filter(),
                ~db.or_(
                    Appointment.scheduled_end <= window_start,
                    Appointment.scheduled_start >= window_end,
                ),
            )
            .correlate(Technician)
        )

        stmt = (
            db.select(Technician)
            .join(
                TechnicianQualification,
                db.and_(
                    TechnicianQualification.technician_id == Technician.id,
                    TechnicianQualification.service_type_id == service_type_id,
                ),
            )
            .where(
                Technician.dealership_id == dealership_id,
                Technician.is_active == True,
                ~overlap_subq.exists(),
            )
        )
        if technician_id:
            stmt = stmt.where(Technician.id == technician_id)
        return list(db.session.execute(stmt).unique().scalars().all())

    def find_least_loaded_available(
        self,
        dealership_id: str,
        service_type_id: str,
        window_start: datetime,
        window_end: datetime,
        local_day_start_utc: datetime,
        local_day_end_utc: datetime,
    ) -> Technician | None:
        """
        Auto-assign strategy: pick the qualified technician with the fewest active
        appointments (CONFIRMED + unexpired PENDING) on the booking day, breaking
        ties deterministically by technician.id ASC.
        """
        bookings_today_subq = (
            db.select(func.count(Appointment.id))
            .where(
                Appointment.technician_id == Technician.id,
                _active_hold_filter(),
                Appointment.scheduled_start >= local_day_start_utc,
                Appointment.scheduled_start < local_day_end_utc,
            )
            .correlate(Technician)
            .scalar_subquery()
        )

        overlap_subq = (
            db.select(Appointment.id)
            .where(
                Appointment.technician_id == Technician.id,
                _active_hold_filter(),
                ~db.or_(
                    Appointment.scheduled_end <= window_start,
                    Appointment.scheduled_start >= window_end,
                ),
            )
            .correlate(Technician)
        )

        stmt = (
            db.select(Technician)
            .join(
                TechnicianQualification,
                db.and_(
                    TechnicianQualification.technician_id == Technician.id,
                    TechnicianQualification.service_type_id == service_type_id,
                ),
            )
            .where(
                Technician.dealership_id == dealership_id,
                Technician.is_active == True,
                ~overlap_subq.exists(),
            )
            .order_by(bookings_today_subq.asc(), Technician.id.asc())
            .limit(1)
        )
        return db.session.execute(stmt).unique().scalars().first()

    def validate_no_overlap(
        self, technician_id: str, window_start: datetime, window_end: datetime
    ) -> bool:
        """Re-check after advisory lock: True if technician is still free."""
        overlap = db.session.execute(
            db.select(Appointment.id)
            .where(
                Appointment.technician_id == technician_id,
                _active_hold_filter(),
                ~db.or_(
                    Appointment.scheduled_end <= window_start,
                    Appointment.scheduled_start >= window_end,
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        return overlap is None

    # ------------------------------------------------------------------
    # Batch load (calendar view — 3-query approach)
    # ------------------------------------------------------------------

    def load_qualified(
        self,
        dealership_id: str,
        service_type_id: str,
        technician_id: str | None = None,
    ) -> list[Technician]:
        """Query 2 of the batch calendar load."""
        return self.list_qualified(dealership_id, service_type_id, technician_id)
