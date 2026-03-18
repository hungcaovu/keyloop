"""Integration tests for POST /appointments."""

import pytest
from datetime import datetime, timedelta, timezone


def _tomorrow_at(hour=14, minute=0):
    """Return tomorrow 14:00 UTC as a naive datetime."""
    tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, 0)


class TestPostAppointments:
    def test_create_success_auto_assign(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """POST /appointments without technician_id → auto-assigns."""
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   _tomorrow_at(14).isoformat(),
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert "appointment" in body
        appt = body["appointment"]
        assert appt["status"] == "CONFIRMED"
        assert appt["technician"] is not None
        assert appt["service_bay"] is not None

    def test_create_success_with_technician_id(
        self, client, db, dealership, service_type_oil, technician, service_bay, customer, vehicle
    ):
        """POST /appointments with technician_id → direct assignment."""
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   dealership.id,
            "service_type_id": service_type_oil.id,
            "desired_start":   _tomorrow_at(14).isoformat(),
            "technician_id":   technician.id,
            "notes":           "Please check tire pressure too.",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["appointment"]["technician"]["id"] == technician.id  # int, no formatting

    def test_missing_required_fields_returns_400(self, client, db):
        resp = client.post("/appointments", json={"customer_id": "some-id"})
        assert resp.status_code == 400

    def test_nonexistent_dealership_returns_404(
        self, client, db, service_type_oil, customer, vehicle
    ):
        resp = client.post("/appointments", json={
            "customer_id":     customer.id,
            "vehicle_id":      vehicle.id,
            "dealership_id":   "00000000-0000-0000-0000-000000000000",
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
