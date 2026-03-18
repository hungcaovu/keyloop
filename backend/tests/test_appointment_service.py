"""Unit tests for AppointmentService booking logic."""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.appointment_service import AppointmentService
from app.exceptions import ResourceUnavailableError, ValidationError, NotFoundError


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
            assert appt.status == "CONFIRMED"
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

            # First booking succeeds
            appt1 = svc.create_appointment(
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                dealership_id=dealership.id,
                service_type_id=service_type_oil.id,
                desired_start=start,
                technician_id=technician.id,
            )
            assert appt1.status == "CONFIRMED"

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
