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
from app.models.appointment import Appointment
from app.exceptions import NotFoundError, ResourceUnavailableError, ValidationError, NoAvailabilityError
from app.utils.timezone import validate_business_hours, business_hours_utc

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
        service_type = self._require(self.svc_type_repo.get_by_id(service_type_id),  f"ServiceType {service_type_id}")
        customer     = self._require(self.customer_repo.get_by_id(customer_id),       f"Customer {customer_id}")
        vehicle      = self._require(self.vehicle_repo.get_by_id(vehicle_id),         f"Vehicle {vehicle_id}")

        if booked_by_customer_id and booked_by_customer_id != customer_id:
            self._require(
                self.customer_repo.get_by_id(booked_by_customer_id),
                f"booked_by_customer {booked_by_customer_id}",
            )

        # ── Step 2: Compute window ────────────────────────────────────────────
        # desired_start is treated as UTC (naive datetime = UTC)
        now_utc      = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = desired_start if desired_start.tzinfo is None else desired_start.replace(tzinfo=None)
        window_end   = window_start + timedelta(minutes=service_type.duration_minutes)

        # Min lead time (A19 variant)
        if window_start < now_utc + timedelta(hours=MIN_LEAD_TIME_HOURS):
            raise ValidationError(
                f"desired_start must be at least {MIN_LEAD_TIME_HOURS} hour(s) in the future.",
                field="desired_start",
            )

        # Max horizon (A17)
        if window_start > now_utc + timedelta(days=BOOKING_HORIZON_DAYS):
            raise ValidationError(
                f"desired_start cannot be more than {BOOKING_HORIZON_DAYS} days in the future.",
                field="desired_start",
            )

        # Business hours (A3)
        if not validate_business_hours(window_start, window_end, dealership.timezone):
            raise ValidationError(
                f"The appointment window must fit within business hours (08:00–18:00 "
                f"{dealership.timezone}). A {service_type.duration_minutes}-min service "
                f"starting at the requested time would end outside business hours.",
                field="desired_start",
            )

        logger.debug(
            "appointment.window_computed",
            extra={
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "dealership_timezone": dealership.timezone,
            },
        )

        # ── Step 3: Resolve technician ────────────────────────────────────────
        local_day_start, local_day_end = business_hours_utc(window_start.date(), dealership.timezone)

        if technician_id:
            logger.debug("appointment.path_b", extra={"requested_technician_id": technician_id})
            # PATH B: Validate technician belongs to dealership (A16) and is available
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
            logger.debug("appointment.path_a", extra={"dealership_id": dealership_id})
            # PATH A: Auto-assign least-loaded qualified technician
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
        bay = available_bays[0]  # always auto-assigned (A8)

        # ── Step 5: Lock → Re-check → INSERT (atomic, correct order) ────────────
        #
        # ORDER MATTERS:
        #   1. acquire_locks()      — serialise concurrent requests for same resource+day
        #   2. validate_no_overlap  — re-check AFTER lock, BEFORE INSERT (closes TOCTOU window)
        #   3. insert()             — write the row only after re-check passes
        #
        # If re-check ran AFTER flush() (inside create()), the just-inserted row would be
        # visible to the SELECT and always trigger a false conflict → rollback every time.
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
            "appointment.create.success",
            extra={
                "appointment_id": appointment.id,
                "technician_id": technician.id,
                "service_bay_id": bay.id,
                "scheduled_start": window_start.isoformat(),
                "scheduled_end": window_end.isoformat(),
                "status": appointment.status,
            },
        )
        return appointment

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
