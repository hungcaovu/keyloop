"""Integration tests for POST /appointments and PATCH confirm/cancel."""

import pytest
from datetime import datetime, timedelta, timezone


def _tomorrow_at(hour=14, minute=0):
    """Return tomorrow 14:00 UTC as a naive datetime."""
    tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, 0)


def _post_appointment(client, customer, vehicle, dealership, service_type_oil, technician=None, hour=14):
    """Helper: POST /appointments and return (resp, body)."""
    payload = {
        "customer_id":     customer.id,
        "vehicle_id":      vehicle.id,
        "dealership_id":   dealership.id,
        "service_type_id": service_type_oil.id,
        "desired_start":   _tomorrow_at(hour).isoformat(),
    }
    if technician:
        payload["technician_id"] = technician.id
    resp = client.post("/appointments", json=payload)
    return resp, resp.get_json()


class TestPostAppointments:
    def test_create_success_auto_assign(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """POST /appointments without technician_id → 202 PENDING with expires_at."""
        resp, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        assert resp.status_code == 202
        assert "appointment" in body
        appt = body["appointment"]
        assert appt["status"] == "PENDING"
        assert appt["technician"] is not None
        assert appt["service_bay"] is not None
        assert appt["expires_at"] is not None

    def test_create_success_with_technician_id(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """POST /appointments with technician_id → 202 PENDING, technician assigned."""
        resp, body = _post_appointment(
            client, customer, vehicle, dealership, service_type_oil, technician=technician
        )
        assert resp.status_code == 202
        assert body["appointment"]["technician"]["id"] == technician.id
        assert body["appointment"]["status"] == "PENDING"

    def test_missing_required_fields_returns_400(self, client, db):
        resp = client.post("/appointments", json={"customer_id": "some-id"})
        assert resp.status_code == 400

    def test_nonexistent_dealership_returns_404(
        self, client, db, service_type_oil, customer, vehicle
    ):
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   999999,
            "service_type_id": service_type_oil.id,
            "desired_start":   _tomorrow_at(14).isoformat(),
        })
        assert resp.status_code == 404

    def test_past_start_time_returns_400(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   past.isoformat(),
        })
        assert resp.status_code == 400

    def test_no_bay_available_returns_409(
        self, client, db, dealership, service_type_oil, technician, customer, vehicle
    ):
        """No service bays in DB → 409 Conflict."""
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   _tomorrow_at(14).isoformat(),
        })
        assert resp.status_code == 409
        body = resp.get_json()
        assert "ResourceUnavailable" in body.get("error", "") or "unavailable" in str(body).lower()


    def test_outside_business_hours_returns_400(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """03:00 UTC = 22:00 CDT — outside 08:00-18:00 business hours."""
        start = _tomorrow_at(3)  # 03:00 UTC
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   start.isoformat(),
        })
        assert resp.status_code == 400
        assert "business hours" in resp.get_json().get("error", "").lower()

    def test_beyond_90_days_returns_400(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        from datetime import datetime, timedelta, timezone
        far_future = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=91))
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   far_future.isoformat(),
        })
        assert resp.status_code == 400


class TestConfirmAppointment:
    def test_confirm_success(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """POST → 202 PENDING → PATCH /confirm → 200 CONFIRMED, expires_at cleared."""
        resp, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        assert resp.status_code == 202
        appt_id = body["appointment"]["id"]

        resp2 = client.patch(f"/appointments/{appt_id}/confirm")
        assert resp2.status_code == 200
        confirmed = resp2.get_json()["appointment"]
        assert confirmed["status"] == "CONFIRMED"
        assert confirmed["expires_at"] is None

    def test_confirm_not_found(self, client, db):
        """PATCH /confirm on non-existent id → 404."""
        resp = client.patch("/appointments/99999/confirm")
        assert resp.status_code == 404

    def test_confirm_already_confirmed_raises_422(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Confirming an already-CONFIRMED appointment → 422 InvalidState."""
        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]
        client.patch(f"/appointments/{appt_id}/confirm")          # first confirm
        resp = client.patch(f"/appointments/{appt_id}/confirm")   # second confirm
        assert resp.status_code == 422

    def test_confirm_expired_hold_returns_409(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Confirm after TTL elapsed → 409 HoldExpired."""
        from app.extensions import db as _db
        from app.models.appointment import Appointment
        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]

        # Manually expire the hold
        appt = _db.session.get(Appointment, appt_id)
        appt.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        _db.session.commit()

        resp = client.patch(f"/appointments/{appt_id}/confirm")
        assert resp.status_code == 409
        body2 = resp.get_json()
        assert body2["error"] == "HoldExpired"


class TestCancelAppointment:
    def test_cancel_pending(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PATCH /cancel on PENDING → 200 CANCELLED."""
        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]

        resp = client.patch(f"/appointments/{appt_id}/cancel")
        assert resp.status_code == 200
        assert resp.get_json()["appointment"]["status"] == "CANCELLED"

    def test_cancel_confirmed(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """PATCH /cancel on CONFIRMED → 200 CANCELLED."""
        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]
        client.patch(f"/appointments/{appt_id}/confirm")

        resp = client.patch(f"/appointments/{appt_id}/cancel")
        assert resp.status_code == 200
        assert resp.get_json()["appointment"]["status"] == "CANCELLED"

    def test_cancel_not_found(self, client, db):
        resp = client.patch("/appointments/99999/cancel")
        assert resp.status_code == 404

    def test_cancel_already_cancelled_returns_422(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """Cancelling an already-CANCELLED appointment → 422."""
        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]
        client.patch(f"/appointments/{appt_id}/cancel")           # first cancel
        resp = client.patch(f"/appointments/{appt_id}/cancel")    # second cancel
        assert resp.status_code == 422

    def test_pending_slot_freed_after_cancel(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """After cancelling a PENDING hold, the same slot can be booked again."""
        from app.models.customer import Customer as CustomerModel
        from app.models.vehicle import Vehicle as VehicleModel
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        _, body = _post_appointment(client, customer, vehicle, dealership, service_type_oil)
        appt_id = body["appointment"]["id"]
        client.patch(f"/appointments/{appt_id}/cancel")

        # New customer + vehicle
        c2 = CustomerModel(first_name="Bob", last_name="Jones", email="bob@test.com", created_at=now)
        db.session.add(c2); db.session.flush()
        v2 = VehicleModel(customer_id=c2.id, make="Toyota", model="Camry", year=2021, created_at=now)
        db.session.add(v2); db.session.flush()
        db.session.commit()

        resp2 = client.post("/appointments", json={
            "customer_id":     c2.id,
            "vehicle_id":      v2.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   _tomorrow_at(14).isoformat(),
            "technician_id":   technician.id,
        })
        assert resp2.status_code == 202


class TestGetDealerships:
    def test_search_dealerships(self, client, db, dealership):
        resp = client.get("/dealerships?q=Test")
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body["data"], list)

    def test_search_too_short(self, client, db):
        resp = client.get("/dealerships?q=T")
        assert resp.status_code == 400

    def test_list_all(self, client, db, dealership):
        resp = client.get("/dealerships")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) >= 1


class TestGetServiceTypes:
    def test_list_all(self, client, db, service_type_oil):
        resp = client.get("/service-types")
        assert resp.status_code == 200
        body = resp.get_json()
        assert any(st["name"] == "Oil Change" for st in body["data"])

    def test_search_by_name(self, client, db, service_type_oil):
        resp = client.get("/service-types?q=Oil")
        assert resp.status_code == 200
        body = resp.get_json()
        assert any(st["name"] == "Oil Change" for st in body["data"])

    def test_search_too_short(self, client, db):
        resp = client.get("/service-types?q=O")
        assert resp.status_code == 400
