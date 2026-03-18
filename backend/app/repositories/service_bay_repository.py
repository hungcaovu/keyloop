from __future__ import annotations
from datetime import datetime
from app.extensions import db
from app.models.service_bay import ServiceBay
from app.models.appointment import Appointment, AppointmentStatus


class ServiceBayRepository:
    def get_by_id(self, bay_id: str) -> ServiceBay | None:
        return db.session.get(ServiceBay, bay_id)

    def load_compatible(self, dealership_id: str, bay_type: str) -> list[ServiceBay]:
        """Query 3 of the batch calendar load: all active compatible bays."""
        return list(
            db.session.execute(
                db.select(ServiceBay).where(
                    ServiceBay.dealership_id == dealership_id,
                    ServiceBay.bay_type == bay_type,
                    ServiceBay.is_active == True,
                )
            ).scalars().all()
        )

    def find_available(
        self,
        dealership_id: str,
        bay_type: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ServiceBay]:
        """Return compatible bays with NO overlapping CONFIRMED appointment."""
        overlap_subq = (
            db.select(Appointment.id)
            .where(
                Appointment.service_bay_id == ServiceBay.id,
                Appointment.status == AppointmentStatus.CONFIRMED.value,
                ~db.or_(
                    Appointment.scheduled_end <= window_start,
                    Appointment.scheduled_start >= window_end,
                ),
            )
            .correlate(ServiceBay)
        )

        return list(
            db.session.execute(
                db.select(ServiceBay).where(
                    ServiceBay.dealership_id == dealership_id,
                    ServiceBay.bay_type == bay_type,
                    ServiceBay.is_active == True,
                    ~overlap_subq.exists(),
                )
            ).scalars().all()
        )

    def count_available(
        self,
        dealership_id: str,
        bay_type: str,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        return len(self.find_available(dealership_id, bay_type, window_start, window_end))

    def validate_no_overlap(
        self, service_bay_id: str, window_start: datetime, window_end: datetime
    ) -> bool:
        """Re-check after advisory lock: True if bay is still free."""
        overlap = db.session.execute(
            db.select(Appointment.id)
            .where(
                Appointment.service_bay_id == service_bay_id,
                Appointment.status == AppointmentStatus.CONFIRMED.value,
                ~db.or_(
                    Appointment.scheduled_end <= window_start,
                    Appointment.scheduled_start >= window_end,
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        return overlap is None
