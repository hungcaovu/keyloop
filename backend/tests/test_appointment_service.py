"""Unit tests for AppointmentService booking logic."""

import logging
import pytest
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from app.services.appointment_service import AppointmentService
from app.exceptions import (
    ResourceUnavailableError, ValidationError, NotFoundError,
    HoldExpiredError, InvalidStateError,
)


def _future(hours=2):
    """Return a naive UTC datetime N hours from now."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours)


class TestAppointmentService:
    def test_create_appointment_auto_assign_success(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PATH A — no technician_id provided, auto-assigns least-loaded."""
        with app.app_context():
            svc = AppointmentService()
            # Oil change = 30 min → 09:00–09:30 UTC which is 04:00–04:30 CDT... wait
            # Actually dealership is America/Chicago (CDT = UTC-5 in March 2026 after DST)
            # Business hours 08:00–18:00 CDT = 13:00–23:00 UTC
            # So pick 14:00 UTC = 09:00 CDT (within business hours)
            start = _future(hours=2)
            # Adjust to 14:00 UTC today to be in business hours for Chicago
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            appt = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
            )
            assert appt.id is not None
            assert appt.status == "PENDING"
            assert appt.expires_at is not None
            assert appt.technician_id == technician.id
            assert appt.service_bay_id == service_bay.id

    def test_create_appointment_with_specific_technician(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PATH B — technician_id provided, assigned directly."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            appt = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )
            assert appt.technician_id == technician.id

    def test_booking_outside_business_hours_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Desired start at 03:00 UTC (outside Chicago business hours) must raise ValidationError."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            # 03:00 UTC = 22:00 CDT — well outside business hours
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 3, 0, 0)

            with pytest.raises(ValidationError) as exc_info:
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=start,
                )
            assert "business hours" in exc_info.value.message.lower()

    def test_booking_in_the_past_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        with app.app_context():
            svc = AppointmentService()
            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            with pytest.raises(ValidationError) as exc_info:
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=past,
                )
            assert "future" in exc_info.value.message.lower()

    def test_booking_beyond_90_days_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        with app.app_context():
            svc = AppointmentService()
            far_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=91)
            with pytest.raises(ValidationError):
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=far_future,
                )

    def test_no_bay_raises_resource_unavailable(
        self, db, app, dealership, service_type_oil, technician, customer, vehicle
    ):
        """With no service bays, booking must fail with ResourceUnavailableError."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            with pytest.raises(ResourceUnavailableError):
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=start,
                )

    def test_double_booking_same_slot_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """A second booking for the same slot with the same technician must fail."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            # First booking succeeds (PENDING hold)
            appt1 = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )
            assert appt1.status == "PENDING"

            # Second booking same slot same technician must fail
            from app.models.customer import Customer as CustomerModel
            from app.models.vehicle import Vehicle as VehicleModel
            c2 = CustomerModel(first_name="Other", last_name="Person", email="other@test.com", created_at=datetime.now(timezone.utc).replace(tzinfo=None))
            db.session.add(c2)
            db.session.flush()  # flush now so c2.id is populated
            v2 = VehicleModel(customer_id=c2.id, make="Toyota", model="Camry", year=2020, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
            db.session.add(v2)
            db.session.flush()

            with pytest.raises(ResourceUnavailableError):
                svc.create_appointment(
                    customer_id=c2.id,
                    vehicle_id=v2.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=start,
                    technician_id=technician.id,
                )

    def test_booking_within_lead_time_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """desired_start < now + 1h must raise ValidationError."""
        with app.app_context():
            svc = AppointmentService()
            # 30 minutes from now is inside the 1-hour minimum
            almost_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
            with pytest.raises(ValidationError) as exc_info:
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_oil.id,
                    desired_start=almost_now,
                )
            assert "future" in exc_info.value.message.lower()

    def test_unqualified_technician_in_path_b_raises(
        self, db, app, dealership, service_type_oil, service_type_brake,
        technician, service_bay_lift, customer, vehicle
    ):
        """PATH B: requesting a technician not qualified for the service type must fail."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            # technician is qualified for oil but NOT for brake inspection
            with pytest.raises(ResourceUnavailableError):
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_brake.id,  # brake — tech not qualified
                    desired_start=start,
                    technician_id=technician.id,
                )

    def test_no_compatible_bay_type_raises(
        self, db, app, dealership, service_type_brake, technician_brake, service_bay, customer, vehicle
    ):
        """Brake inspection needs LIFT bay; only GENERAL bay available → ResourceUnavailableError."""
        with app.app_context():
            svc = AppointmentService()
            today = datetime.now(timezone.utc).replace(tzinfo=None).date()
            tomorrow = today + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            # service_bay is GENERAL, brake inspection requires LIFT
            with pytest.raises(ResourceUnavailableError):
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id=dealership.id,
                    service_type_id=service_type_brake.id,
                    desired_start=start,
                )

    def test_nonexistent_dealership_raises(self, db, app, customer, vehicle, service_type_oil):
        with app.app_context():
            svc = AppointmentService()
            tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)
            with pytest.raises(NotFoundError):
                svc.create_appointment(
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    dealership_id="00000000-0000-0000-0000-000000000000",
                    service_type_id=service_type_oil.id,
                    desired_start=start,
                )

    # ── confirm_appointment ────────────────────────────────────────────────────

    def _make_pending(self, svc, customer, vehicle, dealership, service_type_oil):
        """Helper: create a PENDING appointment and return it."""
        tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
        start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)
        return svc.create_appointment(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            dealership_id=dealership.id,
            service_type_id=service_type_oil.id,
            desired_start=start,
        )

    def test_confirm_appointment_success(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PENDING → confirm → CONFIRMED, expires_at cleared."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            assert appt.status == "PENDING"

            confirmed = svc.confirm_appointment(appt.id)
            assert confirmed.status == "CONFIRMED"
            assert confirmed.expires_at is None

    def test_confirm_not_found_raises(self, db, app):
        with app.app_context():
            svc = AppointmentService()
            with pytest.raises(NotFoundError):
                svc.confirm_appointment(999999)

    def test_confirm_already_confirmed_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Confirming a non-PENDING appointment raises InvalidStateError."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            svc.confirm_appointment(appt.id)
            with pytest.raises(InvalidStateError):
                svc.confirm_appointment(appt.id)

    def test_confirm_expired_hold_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Confirming after TTL expired raises HoldExpiredError."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            # Expire the hold manually
            appt.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
            db.session.commit()

            with pytest.raises(HoldExpiredError):
                svc.confirm_appointment(appt.id)

    # ── cancel_appointment ─────────────────────────────────────────────────────

    def test_cancel_pending_appointment(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PENDING → cancel → CANCELLED."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            cancelled = svc.cancel_appointment(appt.id)
            assert cancelled.status == "CANCELLED"

    def test_cancel_confirmed_appointment(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """CONFIRMED → cancel → CANCELLED."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            svc.confirm_appointment(appt.id)
            cancelled = svc.cancel_appointment(appt.id)
            assert cancelled.status == "CANCELLED"

    def test_cancel_not_found_raises(self, db, app):
        with app.app_context():
            svc = AppointmentService()
            with pytest.raises(NotFoundError):
                svc.cancel_appointment(999999)

    def test_cancel_already_cancelled_raises(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Cancelling an already-CANCELLED appointment raises InvalidStateError."""
        with app.app_context():
            svc = AppointmentService()
            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            svc.cancel_appointment(appt.id)
            with pytest.raises(InvalidStateError):
                svc.cancel_appointment(appt.id)

    def test_calendar_shows_one_tech_when_two_pending_holds(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        3 techs qualified for the same service, 2 have unexpired PENDING holds
        at the same slot. Calendar must show that slot with technician_count=1.

        Setup:
          - T1 (technician fixture), T2, T3 — all oil-change qualified
          - B1 (service_bay fixture), B2, B3 — all GENERAL bays
          - appt1: T1 + B1 PENDING at slot_start
          - appt2: T2 + B2 PENDING at slot_start
          - T3 + B3 remain free
        Expected:
          get_calendar_slots returns the slot at slot_start with technician_count=1.
        """
        from app.models.technician import Technician as TechnicianModel, TechnicianQualification
        from app.models.service_bay import ServiceBay
        from app.models.customer import Customer as CustomerModel
        from app.models.vehicle import Vehicle as VehicleModel
        from app.services.availability_service import AvailabilityService

        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # ── Setup: T2, T3 ──────────────────────────────────────────────────
            t2 = TechnicianModel(
                dealership_id=dealership.id, first_name="Ana", last_name="Garcia",
                employee_number="T-002", is_active=True,
            )
            t3 = TechnicianModel(
                dealership_id=dealership.id, first_name="Ben", last_name="Nguyen",
                employee_number="T-003", is_active=True,
            )
            db.session.add_all([t2, t3])
            db.session.flush()
            for tech in [t2, t3]:
                db.session.add(TechnicianQualification(
                    technician_id=tech.id,
                    service_type_id=service_type_oil.id,
                    certified_at=now,
                ))
            logger.info(
                "[test] technicians created: T1=%s (%s %s), T2=%s (%s %s), T3=%s (%s %s)",
                technician.id, technician.first_name, technician.last_name,
                t2.id, t2.first_name, t2.last_name,
                t3.id, t3.first_name, t3.last_name,
            )

            # ── Setup: B2, B3 (B1 = service_bay fixture) ──────────────────────
            b2 = ServiceBay(dealership_id=dealership.id, bay_number="Bay 2", bay_type="GENERAL", is_active=True)
            b3 = ServiceBay(dealership_id=dealership.id, bay_number="Bay 3", bay_type="GENERAL", is_active=True)
            db.session.add_all([b2, b3])
            db.session.flush()
            logger.info(
                "[test] service bays: B1=%s, B2=%s, B3=%s (all GENERAL)",
                service_bay.id, b2.id, b3.id,
            )

            # ── Setup: second customer + vehicle for appt2 ─────────────────────
            c2 = CustomerModel(first_name="Bob", last_name="Lee", email="bob2@test.com", created_at=now)
            db.session.add(c2)
            db.session.flush()
            v2 = VehicleModel(customer_id=c2.id, make="Toyota", model="Camry", year=2020, created_at=now)
            db.session.add(v2)
            db.session.flush()
            db.session.commit()
            logger.info("[test] second customer C2=%s, vehicle V2=%s", c2.id, v2.id)

            # Target slot: tomorrow 14:00 UTC = 09:00 CDT (inside business hours)
            tomorrow = now.date() + timedelta(days=1)
            slot_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)
            logger.info("[test] target slot: %s UTC (09:00 CDT)", slot_start)

            # ── Book: PENDING hold for T1 + B1 ────────────────────────────────
            svc = AppointmentService()
            appt1 = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=slot_start,
                technician_id=technician.id,   # T1
            )
            assert appt1.status == "PENDING"
            logger.info(
                "[test] appt1 PENDING: id=%s tech=%s bay=%s expires=%s",
                appt1.id, appt1.technician_id, appt1.service_bay_id, appt1.expires_at,
            )

            # ── Book: PENDING hold for T2 + B2 ────────────────────────────────
            appt2 = svc.create_appointment(
                customer_id=c2.id,
                vehicle_id=v2.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=slot_start,
                technician_id=t2.id,           # T2
            )
            assert appt2.status == "PENDING"
            logger.info(
                "[test] appt2 PENDING: id=%s tech=%s bay=%s expires=%s",
                appt2.id, appt2.technician_id, appt2.service_bay_id, appt2.expires_at,
            )

            logger.info(
                "[test] state: T1+T2 booked (PENDING), T3=%s free; B1+B2 booked, B3=%s free",
                t3.id, b3.id,
            )

            # ── Check calendar ─────────────────────────────────────────────────
            avail_svc = AvailabilityService()
            result = avail_svc.get_calendar_slots(
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                from_date=tomorrow,
                days=1,
            )

            all_slots = [s for day in result.slots for s in day.available_times]
            logger.info(
                "[test] calendar returned %d slot(s) for %s",
                len(all_slots), tomorrow,
            )
            for s in all_slots:
                logger.info(
                    "[test]   slot %s–%s  technician_count=%d  bay_count=%d",
                    s.start.strftime("%H:%M"), s.end.strftime("%H:%M"), s.technician_count, s.bay_count,
                )

            target = [s for s in all_slots if s.start == slot_start]
            logger.info(
                "[test] slot at %s UTC → technician_count=%s (expected 1)",
                slot_start, target[0].technician_count if target else "NOT FOUND",
            )
            assert len(target) == 1, (
                f"Expected slot at {slot_start} to be present, found {len(target)}"
            )
            assert target[0].technician_count == 1, (
                f"Expected technician_count=1 (only T3 free), got {target[0].technician_count}"
            )
            logger.info("[test] PASSED — technician_count=1 correctly reflects 2 PENDING holds")

    def test_calendar_slot_hidden_when_all_bays_pending(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        3 techs, only 2 bays. Both bays get PENDING holds at the same slot.
        Even though T3 is free, NO bay is available → the slot must NOT appear
        in the calendar at that time.

        Setup:
          - T1, T2, T3 — all oil-change qualified
          - B1 (service_bay fixture), B2 — only 2 GENERAL bays (no B3)
          - appt1: T1 + B1 PENDING at slot_start
          - appt2: T2 + B2 PENDING at slot_start
          - T3 free, but ALL bays occupied → slot absent from calendar
        Expected:
          get_calendar_slots returns NO slot at slot_start.
        """
        from app.models.technician import Technician as TechnicianModel, TechnicianQualification
        from app.models.service_bay import ServiceBay
        from app.models.customer import Customer as CustomerModel
        from app.models.vehicle import Vehicle as VehicleModel
        from app.services.availability_service import AvailabilityService

        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # ── Setup: T2, T3 ──────────────────────────────────────────────────
            t2 = TechnicianModel(
                dealership_id=dealership.id, first_name="Ana", last_name="Garcia",
                employee_number="T-002", is_active=True,
            )
            t3 = TechnicianModel(
                dealership_id=dealership.id, first_name="Ben", last_name="Nguyen",
                employee_number="T-003", is_active=True,
            )
            db.session.add_all([t2, t3])
            db.session.flush()
            for tech in [t2, t3]:
                db.session.add(TechnicianQualification(
                    technician_id=tech.id,
                    service_type_id=service_type_oil.id,
                    certified_at=now,
                ))
            logger.info(
                "[test] technicians: T1=%s (%s %s), T2=%s (%s %s), T3=%s (%s %s)",
                technician.id, technician.first_name, technician.last_name,
                t2.id, t2.first_name, t2.last_name,
                t3.id, t3.first_name, t3.last_name,
            )

            # ── Setup: B2 only — no B3 (only 2 bays total) ────────────────────
            b2 = ServiceBay(dealership_id=dealership.id, bay_number="Bay 2", bay_type="GENERAL", is_active=True)
            db.session.add(b2)
            db.session.flush()
            logger.info(
                "[test] service bays: B1=%s, B2=%s (only 2 GENERAL bays — no B3)",
                service_bay.id, b2.id,
            )

            # ── Setup: second customer + vehicle for appt2 ─────────────────────
            c2 = CustomerModel(first_name="Bob", last_name="Lee", email="bob2@test.com", created_at=now)
            db.session.add(c2)
            db.session.flush()
            v2 = VehicleModel(customer_id=c2.id, make="Toyota", model="Camry", year=2020, created_at=now)
            db.session.add(v2)
            db.session.flush()
            db.session.commit()
            logger.info("[test] second customer C2=%s, vehicle V2=%s", c2.id, v2.id)

            # Target slot: tomorrow 14:00 UTC = 09:00 CDT
            tomorrow = now.date() + timedelta(days=1)
            slot_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)
            logger.info("[test] target slot: %s UTC (09:00 CDT)", slot_start)

            # ── Book: PENDING hold for T1 + B1 ────────────────────────────────
            svc = AppointmentService()
            appt1 = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=slot_start,
                technician_id=technician.id,   # T1
            )
            assert appt1.status == "PENDING"
            logger.info(
                "[test] appt1 PENDING: id=%s tech=%s bay=%s expires=%s",
                appt1.id, appt1.technician_id, appt1.service_bay_id, appt1.expires_at,
            )

            # ── Book: PENDING hold for T2 + B2 ────────────────────────────────
            appt2 = svc.create_appointment(
                customer_id=c2.id,
                vehicle_id=v2.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=slot_start,
                technician_id=t2.id,           # T2
            )
            assert appt2.status == "PENDING"
            logger.info(
                "[test] appt2 PENDING: id=%s tech=%s bay=%s expires=%s",
                appt2.id, appt2.technician_id, appt2.service_bay_id, appt2.expires_at,
            )

            logger.info(
                "[test] state: T1+T2 booked (PENDING), T3=%s free; B1+B2 ALL booked — no free bay",
                t3.id,
            )

            # ── Check calendar ─────────────────────────────────────────────────
            avail_svc = AvailabilityService()
            result = avail_svc.get_calendar_slots(
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                from_date=tomorrow,
                days=1,
            )

            all_slots = [s for day in result.slots for s in day.available_times]
            logger.info(
                "[test] calendar returned %d slot(s) for %s",
                len(all_slots), tomorrow,
            )
            for s in all_slots:
                logger.info(
                    "[test]   slot %s–%s  technician_count=%d  bay_count=%d",
                    s.start.strftime("%H:%M"), s.end.strftime("%H:%M"), s.technician_count, s.bay_count,
                )

            target = [s for s in all_slots if s.start == slot_start]
            logger.info(
                "[test] slot at %s UTC → %s (expected: absent — no free bay)",
                slot_start, f"technician_count={target[0].technician_count}" if target else "NOT FOUND",
            )
            assert len(target) == 0, (
                f"Expected slot at {slot_start} to be ABSENT (all bays taken), "
                f"but found it with technician_count={target[0].technician_count}"
            )
            logger.info("[test] PASSED — slot correctly hidden when all bays are occupied by PENDING holds")

    def test_calendar_counts_correct_no_id_namespace_collision(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """
        Regression test: tech IDs and bay IDs share the same integer namespace
        (both auto-increment from 1). A booked bay must NOT mark a tech with the
        same numeric ID as busy, and vice-versa.

        Setup:
          - T1 (fixture id=1), T2 (id=2), T3 (id=3), T4 (id=4) — all oil-qualified
          - B1 (fixture id=1), B2 (id=2) — both GENERAL bays
          Booking: T3 + auto-bay → system picks B1 (lowest id available)
            → bay_booked[1] = [(s,e)]   (B1 is busy)
            → tech_booked[3] = [(s,e)]  (T3 is busy)

        With the old flat dict bug:
          booked[1] = [(s,e)] — shared by T1 and B1
          booked[3] = [(s,e)] — T3
          → T1 (id=1) incorrectly sees B1's interval → marked as blocked
          → technician_count=2 instead of 3  ← the user-reported bug

        With the fix (separate tech_booked / bay_booked dicts):
          → technician_count=3 (T1, T2, T4 free), bay_count=1 (B2 free)
        """
        from app.models.technician import Technician as TechnicianModel, TechnicianQualification
        from app.models.service_bay import ServiceBay
        from app.services.availability_service import AvailabilityService

        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # ── Add T2, T3, T4 (T1 = technician fixture) ──────────────────────
            t2 = TechnicianModel(dealership_id=dealership.id, first_name="Ana", last_name="Garcia",
                                 employee_number="T-002", is_active=True)
            t3 = TechnicianModel(dealership_id=dealership.id, first_name="Ben", last_name="Nguyen",
                                 employee_number="T-003", is_active=True)
            t4 = TechnicianModel(dealership_id=dealership.id, first_name="Dia", last_name="Kim",
                                 employee_number="T-004", is_active=True)
            db.session.add_all([t2, t3, t4])
            db.session.flush()
            for tech in [t2, t3, t4]:
                db.session.add(TechnicianQualification(
                    technician_id=tech.id,
                    service_type_id=service_type_oil.id,
                    certified_at=now,
                ))

            # ── Add B2 (B1 = service_bay fixture) ─────────────────────────────
            b2 = ServiceBay(dealership_id=dealership.id, bay_number="Bay 2",
                            bay_type="GENERAL", is_active=True)
            db.session.add(b2)
            db.session.flush()
            db.session.commit()

            logger.info(
                "[test] techs T1=%s T2=%s T3=%s T4=%s | bays B1=%s B2=%s",
                technician.id, t2.id, t3.id, t4.id, service_bay.id, b2.id,
            )
            # Verify the collision condition: T1.id == B1.id (both should be 1 in SQLite)
            logger.info(
                "[test] collision check: T1.id=%s == B1.id=%s → %s",
                technician.id, service_bay.id, technician.id == service_bay.id,
            )

            # ── Book T3 + auto-bay (system will pick B1, the lowest-id free bay) ──
            tomorrow = now.date() + timedelta(days=1)
            slot_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)

            svc = AppointmentService()
            appt = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=slot_start,
                technician_id=t3.id,   # explicitly T3, auto-selects bay
            )
            assert appt.technician_id == t3.id
            logger.info(
                "[test] booked: tech=%s bay=%s — bay.id=%s should equal T1.id=%s",
                appt.technician_id, appt.service_bay_id, appt.service_bay_id, technician.id,
            )

            # ── Calendar check ─────────────────────────────────────────────────
            avail_svc = AvailabilityService()
            result = avail_svc.get_calendar_slots(
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                from_date=tomorrow,
                days=1,
            )
            all_slots = [s for day in result.slots for s in day.available_times]
            target = next((s for s in all_slots if s.start == slot_start), None)

            logger.info(
                "[test] slot at 14:00 UTC → technician_count=%s bay_count=%s "
                "(expected 3 techs free: T1,T2,T4; 1 bay free: B2)",
                target.technician_count if target else "ABSENT",
                target.bay_count if target else "ABSENT",
            )

            assert target is not None, "Slot should still be visible (B2 and T1/T2/T4 are free)"
            assert target.technician_count == 3, (
                f"Expected 3 free techs (T1,T2,T4), got {target.technician_count}. "
                f"If got 2, the flat-namespace collision bug is present."
            )
            assert target.bay_count == 1, (
                f"Expected 1 free bay (B2), got {target.bay_count}"
            )

    def test_pending_slot_freed_after_cancel(
        self, db, app, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """After cancelling a PENDING hold the slot becomes bookable again."""
        from app.models.customer import Customer as CustomerModel
        from app.models.vehicle import Vehicle as VehicleModel

        with app.app_context():
            svc = AppointmentService()
            tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
            start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 14, 0, 0)
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            appt = self._make_pending(svc, customer, vehicle, dealership, service_type_oil)
            svc.cancel_appointment(appt.id)

            # Different customer + vehicle, same slot
            c2 = CustomerModel(first_name="Bob", last_name="Jones", email="bob@test.com", created_at=now)
            db.session.add(c2); db.session.flush()
            v2 = VehicleModel(customer_id=c2.id, make="Toyota", model="Camry", year=2021, created_at=now)
            db.session.add(v2); db.session.flush(); db.session.commit()

            appt2 = svc.create_appointment(
                customer_id=c2.id,
                vehicle_id=v2.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )
            assert appt2.status == "PENDING"
