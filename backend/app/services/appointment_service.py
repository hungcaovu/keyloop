from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from app.extensions import db

logger = logging.getLogger(__name__)
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.technician_repository import TechnicianRepository
from app.repositories.service_bay_repository import ServiceBayRepository
from app.repositories.service_type_repository import ServiceTypeRepository
from app.repositories.dealership_repository import DealershipRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.vehicle_repository import VehicleRepository
from app.services.availability_service import AvailabilityService
from app.models.appointment import Appointment, AppointmentStatus
from app.exceptions import (
    NotFoundError, ResourceUnavailableError, ValidationError,
    NoAvailabilityError, HoldExpiredError, InvalidStateError,
)
from app.utils.timezone import validate_business_hours, business_hours_utc, validate_timezone_str

BOOKING_HORIZON_DAYS = 90
MIN_LEAD_TIME_HOURS  = 1


class AppointmentService:
    def __init__(self):
        self.appt_repo        = AppointmentRepository()
        self.tech_repo        = TechnicianRepository()
        self.bay_repo         = ServiceBayRepository()
        self.svc_type_repo    = ServiceTypeRepository()
        self.dealership_repo  = DealershipRepository()
        self.customer_repo    = CustomerRepository()
        self.vehicle_repo     = VehicleRepository()
        self.availability_svc = AvailabilityService()

    def create_appointment(
        self,
        customer_id: str,
        vehicle_id: str,
        dealership_id: str,
        service_type_id: str,
        desired_start: datetime,
        technician_id: str | None = None,
        booked_by_customer_id: str | None = None,
        notes: str | None = None,
    ) -> Appointment:
        """
        Phase 1 — create a PENDING soft hold.

        Validates all entities, resolves resources, acquires advisory locks,
        re-checks for conflicts, then INSERTs with status=PENDING and
        expires_at = now + 10 minutes.

        Returns the PENDING appointment. The caller (route) returns 202 Accepted.
        The advisor must call confirm_appointment() within the TTL.
        """
        logger.info(
            "appointment.create.start",
            extra={
                "customer_id": customer_id,
                "vehicle_id": vehicle_id,
                "dealership_id": dealership_id,
                "service_type_id": service_type_id,
                "desired_start": desired_start.isoformat() if desired_start else None,
                "technician_id": technician_id,
            },
        )

        # ── Step 1: Validate referenced entities ──────────────────────────────
        dealership   = self._require(self.dealership_repo.get_by_id(dealership_id),  f"Dealership {dealership_id}")
        try:
            validate_timezone_str(dealership.timezone)
        except ValueError as e:
            raise ValidationError(str(e), field="dealership_id")
        service_type = self._require(self.svc_type_repo.get_by_id(service_type_id),  f"ServiceType {service_type_id}")
        customer     = self._require(self.customer_repo.get_by_id(customer_id),       f"Customer {customer_id}")
        vehicle      = self._require(self.vehicle_repo.get_by_id(vehicle_id),         f"Vehicle {vehicle_id}")

        if booked_by_customer_id and booked_by_customer_id != customer_id:
            self._require(
                self.customer_repo.get_by_id(booked_by_customer_id),
                f"booked_by_customer {booked_by_customer_id}",
            )

        # ── Step 2: Compute window ────────────────────────────────────────────
        if service_type.duration_minutes <= 0:
            raise ValidationError(
                f"ServiceType '{service_type.name}' has invalid duration ({service_type.duration_minutes} min).",
                field="service_type_id",
            )

        now_utc      = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = desired_start if desired_start.tzinfo is None else desired_start.astimezone(timezone.utc).replace(tzinfo=None)
        window_end   = window_start + timedelta(minutes=service_type.duration_minutes)

        if window_start < now_utc + timedelta(hours=MIN_LEAD_TIME_HOURS):
            raise ValidationError(
                f"desired_start must be at least {MIN_LEAD_TIME_HOURS} hour(s) in the future.",
                field="desired_start",
            )

        if window_start > now_utc + timedelta(days=BOOKING_HORIZON_DAYS):
            raise ValidationError(
                f"desired_start cannot be more than {BOOKING_HORIZON_DAYS} days in the future.",
                field="desired_start",
            )

        if not validate_business_hours(window_start, window_end, dealership.timezone):
            raise ValidationError(
                f"The appointment window must fit within business hours (08:00–18:00 "
                f"{dealership.timezone}). A {service_type.duration_minutes}-min service "
                f"starting at the requested time would end outside business hours.",
                field="desired_start",
            )

        # ── Step 3: Resolve technician ────────────────────────────────────────
        local_day_start, local_day_end = business_hours_utc(window_start.date(), dealership.timezone)

        if technician_id:
            tech_check = self._validate_technician(
                technician_id, dealership_id, service_type_id, window_start, window_end
            )
            if not tech_check:
                next_slot = self._safe_next_slot(dealership_id, service_type_id, window_start)
                raise ResourceUnavailableError(
                    "The requested technician is not available for the selected time slot.",
                    next_available_slot=next_slot,
                )
            technician = tech_check
        else:
            technician = self.tech_repo.find_least_loaded_available(
                dealership_id=dealership_id,
                service_type_id=service_type_id,
                window_start=window_start,
                window_end=window_end,
                local_day_start_utc=local_day_start,
                local_day_end_utc=local_day_end,
            )
            if not technician:
                next_slot = self._safe_next_slot(dealership_id, service_type_id, window_start)
                raise ResourceUnavailableError(
                    "No qualified technician is available for the selected time slot.",
                    next_available_slot=next_slot,
                )

        # ── Step 4: Find available bay ────────────────────────────────────────
        available_bays = self.bay_repo.find_available(
            dealership_id, service_type.required_bay_type, window_start, window_end
        )
        if not available_bays:
            next_slot = self._safe_next_slot(dealership_id, service_type_id, window_start)
            raise ResourceUnavailableError(
                "No compatible service bay is available for the selected time slot.",
                next_available_slot=next_slot,
            )
        bay = available_bays[0]

        # ── Step 5: Lock → Re-check → INSERT PENDING ─────────────────────────
        self.appt_repo.acquire_locks(technician.id, bay.id, window_start, dealership_id)

        tech_still_free = self.tech_repo.validate_no_overlap(technician.id, window_start, window_end)
        bay_still_free  = self.bay_repo.validate_no_overlap(bay.id, window_start, window_end)

        if not tech_still_free or not bay_still_free:
            next_slot = self._safe_next_slot(dealership_id, service_type_id, window_start)
            raise ResourceUnavailableError(
                "A concurrent booking took this slot. Please try the next available slot.",
                next_available_slot=next_slot,
            )

        appointment = self.appt_repo.insert(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            dealership_id=dealership_id,
            service_type_id=service_type_id,
            technician_id=technician.id,
            service_bay_id=bay.id,
            scheduled_start=window_start,
            scheduled_end=window_end,
            notes=notes,
            booked_by_customer_id=booked_by_customer_id or customer_id,
        )

        db.session.commit()
        db.session.refresh(appointment)

        logger.info(
            "appointment.create.pending",
            extra={
                "appointment_id": appointment.id,
                "technician_id": technician.id,
                "service_bay_id": bay.id,
                "scheduled_start": window_start.isoformat(),
                "expires_at": appointment.expires_at.isoformat() if appointment.expires_at else None,
            },
        )
        return appointment

    def confirm_appointment(self, appointment_id: str) -> Appointment:
        """
        Phase 2 — confirm a PENDING hold → CONFIRMED.

        Validates the hold exists, is PENDING, and has not expired.
        Clears expires_at on success.
        """
        appt = self.appt_repo.get_by_id(appointment_id)
        if not appt:
            raise NotFoundError(f"Appointment {appointment_id} not found.")

        if appt.status != AppointmentStatus.PENDING.value:
            raise InvalidStateError(
                f"Appointment is '{appt.status}' — only PENDING appointments can be confirmed."
            )

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if appt.expires_at and appt.expires_at <= now_utc:
            next_slot = self._safe_next_slot(appt.dealership_id, appt.service_type_id, appt.scheduled_start)
            raise HoldExpiredError(
                "The hold has expired. Please select a new time slot.",
                next_available_slot=next_slot,
            )

        self.appt_repo.confirm(appt)
        db.session.commit()
        db.session.refresh(appt)

        logger.info(
            "appointment.confirmed",
            extra={"appointment_id": appt.id, "scheduled_start": appt.scheduled_start.isoformat()},
        )
        return appt

    def cancel_appointment(self, appointment_id: str) -> Appointment:
        """
        Cancel a PENDING or CONFIRMED appointment → CANCELLED.

        COMPLETED appointments cannot be cancelled (422).
        """
        appt = self.appt_repo.get_by_id(appointment_id)
        if not appt:
            raise NotFoundError(f"Appointment {appointment_id} not found.")

        if appt.status == AppointmentStatus.COMPLETED.value:
            raise InvalidStateError("Cannot cancel a completed appointment.")

        if appt.status == AppointmentStatus.CANCELLED.value:
            raise InvalidStateError("Appointment is already cancelled.")

        self.appt_repo.cancel(appt)
        db.session.commit()
        db.session.refresh(appt)

        logger.info(
            "appointment.cancelled",
            extra={"appointment_id": appt.id},
        )
        return appt

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require(self, obj, label: str):
        if obj is None:
            raise NotFoundError(f"{label} not found.")
        return obj

    def _validate_technician(self, technician_id, dealership_id, service_type_id, window_start, window_end):
        """Return Technician if valid and available, None otherwise (including A16 guard)."""
        techs = self.tech_repo.find_available(
            dealership_id, service_type_id, window_start, window_end, technician_id
        )
        return techs[0] if techs else None

    def _safe_next_slot(self, dealership_id: str, service_type_id: str, from_time: datetime):
        try:
            return self.availability_svc.find_next_slot(dealership_id, service_type_id, from_time)
        except NoAvailabilityError:
            return None
