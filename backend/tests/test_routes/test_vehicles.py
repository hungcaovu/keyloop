"""Integration tests for vehicle routes."""

import pytest


class TestGetVehicle:
    def test_get_by_vin(self, client, db, vehicle):
        resp = client.get(f"/vehicles/1HGCM82633A123456")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["vehicle"]["vin"] == "1HGCM82633A123456"

    def test_get_by_id(self, client, db, vehicle):
        resp = client.get(f"/vehicles/{vehicle.id}")
        assert resp.status_code == 200
        body = resp.get_json()
        from app.utils.entity_ref import encode
        assert body["vehicle"]["id"] == encode("vehicle", vehicle.id)

    def test_get_by_vehicle_ref(self, client, db, vehicle_no_vin):
        """V-000001 format lookup → vehicle without VIN."""
        ref = f"V-{vehicle_no_vin.vehicle_number:06d}"
        resp = client.get(f"/vehicles/{ref}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["vehicle"]["vehicle_number"] == vehicle_no_vin.vehicle_number
        assert body["vehicle"]["vehicle_ref"] == ref

    def test_get_by_vehicle_ref_case_insensitive(self, client, db, vehicle_no_vin):
        ref = f"v-{vehicle_no_vin.vehicle_number:06d}"
        resp = client.get(f"/vehicles/{ref}")
        assert resp.status_code == 200

    def test_vehicle_ref_not_found_returns_404(self, client, db):
        resp = client.get("/vehicles/V-999999")
        assert resp.status_code == 404

    def test_invalid_identifier_returns_400(self, client, db):
        resp = client.get("/vehicles/not-a-valid-identifier")
        assert resp.status_code == 400

    def test_vin_not_found_returns_404(self, client, db):
        resp = client.get("/vehicles/ZZZZZZZZZZZZZZZZZ")
        assert resp.status_code == 404

    def test_nonexistent_id_returns_404(self, client, db):
        resp = client.get("/vehicles/999999")
        assert resp.status_code == 404


class TestPostVehicle:
    def test_create_success_without_vin(self, client, db, customer):
        resp = client.post("/vehicles", json={
            "customer_id": customer.id,
            "make": "Toyota",
            "model": "Camry",
            "year": 2023,
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["vehicle"]["make"] == "Toyota"
        assert body["vehicle"]["vin"] is None
        assert body["vehicle"]["vehicle_number"] is not None
        assert body["vehicle"]["vehicle_ref"].startswith("V-")

    def test_create_success_with_vin(self, client, db, customer):
        resp = client.post("/vehicles", json={
            "customer_id": customer.id,
            "vin": "2T1BURHE0JC034521",
            "make": "Toyota",
            "model": "Corolla",
            "year": 2018,
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["vehicle"]["vin"] == "2T1BURHE0JC034521"
        # VIN vehicles must NOT get a vehicle_ref
        assert body["vehicle"]["vehicle_ref"] is None
        assert body["vehicle"]["vehicle_number"] is None

    def test_duplicate_vin_returns_409(self, client, db, customer, vehicle):
        resp = client.post("/vehicles", json={
            "customer_id": customer.id,
            "vin": "1HGCM82633A123456",   # same as fixture vehicle
            "make": "Honda",
            "model": "Accord",
            "year": 2022,
        })
        assert resp.status_code == 409
        body = resp.get_json()
        assert "existing_vehicle" in body

    def test_missing_required_fields_returns_400(self, client, db, customer):
        resp = client.post("/vehicles", json={"customer_id": customer.id})
        assert resp.status_code == 400

    def test_nonexistent_customer_returns_404(self, client, db):
        resp = client.post("/vehicles", json={
            "customer_id": 999999,
            "make": "Honda",
            "model": "Civic",
            "year": 2020,
        })
        assert resp.status_code == 404


class TestPatchVehicle:
    def test_update_year(self, client, db, vehicle):
        resp = client.patch(f"/vehicles/{vehicle.id}", json={"year": 2023})
        assert resp.status_code == 200
        assert resp.get_json()["vehicle"]["year"] == 2023

    def test_duplicate_vin_on_patch_returns_409(self, client, db, customer, vehicle):
        """Create a second vehicle with different VIN then try to patch it to the first vehicle's VIN."""
        resp = client.post("/vehicles", json={
            "customer_id": customer.id,
            "vin": "2T1BURHE0JC034521",
            "make": "Toyota",
            "model": "Corolla",
            "year": 2020,
        })
        assert resp.status_code == 201
        second_vehicle_id = resp.get_json()["vehicle"]["id"]

        # Try to patch second vehicle to use first vehicle's VIN
        resp = client.patch(f"/vehicles/{second_vehicle_id}", json={"vin": "1HGCM82633A123456"})
        assert resp.status_code == 409

    def test_update_ownership_transfer(self, client, db, vehicle, app):
        from app.models.customer import Customer
        from datetime import datetime, timezone
        with app.app_context():
            from app.extensions import db as _db
            new_owner = Customer(
                first_name="New", last_name="Owner",
                email="new.owner@test.com",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            _db.session.add(new_owner)
            _db.session.commit()
            new_owner_id = new_owner.id

        resp = client.patch(f"/vehicles/{vehicle.id}", json={"customer_id": new_owner_id})
        assert resp.status_code == 200
        from app.utils.entity_ref import encode
        assert resp.get_json()["vehicle"]["customer_id"] == encode("customer", new_owner_id)

    def test_update_not_found(self, client, db):
        resp = client.patch(
            "/vehicles/999999",
            json={"year": 2023},
        )
        assert resp.status_code == 404
