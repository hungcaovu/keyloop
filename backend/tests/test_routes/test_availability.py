"""Integration tests for availability endpoint."""

import pytest
from datetime import datetime, timedelta, timezone


def _tomorrow_str(hour=14, minute=0):
    tomorrow = datetime.now(timezone.utc).replace(tzinfo=None).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute).isoformat()


class TestAvailabilityCalendarMode:
    def test_calendar_no_technician_filter(
        self, client, db, dealership, service_type_oil, technician, service_bay
    ):
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&days=5"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "slots" in body
        assert len(body["slots"]) == 5
        assert "service_type" in body
        assert body["service_type"]["duration_minutes"] == 30

    def test_calendar_with_technician_filter(
        self, client, db, dealership, service_type_oil, technician, service_bay
    ):
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&days=5&technician_id={technician.id}"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["filtered_technician"] is not None
        assert body["filtered_technician"]["id"] == technician.id

    def test_calendar_invalid_dealership_returns_404(self, client, db, service_type_oil):
        resp = client.get(
            f"/dealerships/00000000-0000-0000-0000-000000000000/availability"
            f"?service_type_id={service_type_oil.id}"
        )
        assert resp.status_code == 404

    def test_calendar_missing_service_type_returns_400(self, client, db, dealership):
        resp = client.get(f"/dealerships/{dealership.id}/availability")
        assert resp.status_code == 400

    def test_calendar_days_exceed_max_returns_400(self, client, db, dealership, service_type_oil):
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&days=31"
        )
        assert resp.status_code == 400

    def test_calendar_shows_no_slots_when_no_bays(
        self, client, db, dealership, service_type_oil, technician
    ):
        """No bays → all days should have available_times: []."""
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&days=3"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        for day in body["slots"]:
            assert day["available_times"] == []


class TestAvailabilitySpotCheck:
    def test_spot_check_available(
        self, client, db, dealership, service_type_oil, technician, service_bay
    ):
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&desired_start={_tomorrow_str(14)}"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "available" in body
        assert "available_technicians" in body
        assert "bay_available" in body

    def test_spot_check_no_bays_returns_unavailable(
        self, client, db, dealership, service_type_oil, technician
    ):
        """No bays → spot check must return available: false."""
        resp = client.get(
            f"/dealerships/{dealership.id}/availability"
            f"?service_type_id={service_type_oil.id}&desired_start={_tomorrow_str(14)}"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["available"] is False
        assert body["bay_available"] is False


class TestListTechnicians:
    def test_list_qualified_technicians(
        self, client, db, dealership, service_type_oil, technician
    ):
        resp = client.get(
            f"/dealerships/{dealership.id}/technicians"
            f"?service_type_id={service_type_oil.id}"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == technician.id
        assert body["data"][0]["employee_number"] == "T-001"

    def test_list_technicians_missing_service_type_returns_400(
        self, client, db, dealership
    ):
        resp = client.get(f"/dealerships/{dealership.id}/technicians")
        assert resp.status_code == 400

    def test_list_technicians_invalid_dealership_returns_404(
        self, client, db, service_type_oil
    ):
        resp = client.get(
            f"/dealerships/00000000-0000-0000-0000-000000000000/technicians"
            f"?service_type_id={service_type_oil.id}"
        )
        assert resp.status_code == 404

    def test_unqualified_technician_not_returned(
        self, client, db, dealership, service_type_oil, service_type_brake, technician
    ):
        """technician is only qualified for oil, not brake."""
        resp = client.get(
            f"/dealerships/{dealership.id}/technicians"
            f"?service_type_id={service_type_brake.id}"
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []
