"""Integration tests for customer routes (uses Flask test client + SQLite)."""

import json
import pytest


class TestPostCustomers:
    def test_create_success(self, client, db):
        resp = client.post("/customers", json={
            "first_name": "Test",
            "last_name":  "User",
            "email":      "test.user@example.com",
            "phone":      "+1-555-1234",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert "customer" in body
        assert body["customer"]["email"] == "test.user@example.com"
        assert "warning" not in body or body["warning"] is None

    def test_create_missing_required_field(self, client, db):
        resp = client.post("/customers", json={
            "first_name": "Test",
            # missing last_name, email
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert "error" in body

    def test_create_duplicate_phone_returns_warning(self, client, db, customer):
        resp = client.post("/customers", json={
            "first_name": "Another",
            "last_name":  "Person",
            "email":      "another.person@example.com",
            "phone":      "+1-555-0101",   # same as fixture customer
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert "warning" in body
        assert body["warning"]["code"] == "DUPLICATE_PHONE"

    def test_create_duplicate_email_returns_409(self, client, db, customer):
        resp = client.post("/customers", json={
            "first_name": "Copy",
            "last_name":  "Cat",
            "email":      "jane@test.com",   # same as fixture customer
            "phone":      "+1-555-9999",
        })
        assert resp.status_code == 409


class TestGetCustomer:
    def test_get_by_id_success(self, client, db, customer):
        resp = client.get(f"/customers/{customer.id}")
        assert resp.status_code == 200
        body = resp.get_json()
        from app.utils.entity_ref import encode
        assert body["customer"]["id"] == encode("customer", customer.id)
        # vehicles NOT embedded by default
        assert "vehicles" not in body["customer"]

    def test_get_by_id_not_found(self, client, db):
        resp = client.get("/customers/999999")
        assert resp.status_code == 404

    def test_include_vehicles_empty(self, client, db, customer):
        """?include=vehicles returns vehicles=[] when customer has no vehicles."""
        resp = client.get(f"/customers/{customer.id}?include=vehicles")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "vehicles" in body["customer"]
        assert body["customer"]["vehicles"] == []

    def test_include_vehicles_with_data(self, client, db, customer, vehicle):
        """`?include=vehicles embeds the vehicle list."""
        resp = client.get(f"/customers/{customer.id}?include=vehicles")
        assert resp.status_code == 200
        vehicles = resp.get_json()["customer"]["vehicles"]
        assert len(vehicles) == 1
        assert vehicles[0]["vin"] == "1HGCM82633A123456"

    def test_include_vehicles_contains_vehicle_ref(self, client, db, customer, vehicle_no_vin):
        """VIN-less vehicles embedded with vehicle_ref."""
        resp = client.get(f"/customers/{customer.id}?include=vehicles")
        vehicles = resp.get_json()["customer"]["vehicles"]
        no_vin = next(v for v in vehicles if v["vin"] is None)
        assert no_vin["vehicle_ref"].startswith("V-")

    def test_include_vehicles_multiple_vehicles(self, client, db, customer, vehicle):
        """?include=vehicles with 2 vehicles returns both in the embedded list."""
        client.post("/vehicles", json={
            "customer_id": customer.id,
            "make": "Toyota", "model": "Camry", "year": 2020,
        })
        resp = client.get(f"/customers/{customer.id}?include=vehicles")
        assert resp.status_code == 200
        assert len(resp.get_json()["customer"]["vehicles"]) == 2

    def test_dedicated_vehicles_endpoint_removed(self, client, db, customer):
        """GET /customers/{id}/vehicles is no longer a valid route — use ?include=vehicles."""
        resp = client.get(f"/customers/{customer.id}/vehicles")
        assert resp.status_code == 404

    def test_search_by_phone(self, client, db, customer):
        # phone search is done via q= (merged into unified search)
        resp = client.get("/customers", query_string={"q": "+1-555-0101"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) == 1

    def test_search_without_params_returns_400(self, client, db):
        """Design: q is required."""
        resp = client.get("/customers")
        assert resp.status_code == 400

    def test_search_query_too_short(self, client, db):
        resp = client.get("/customers?q=a")
        assert resp.status_code == 400

    def test_search_by_name(self, client, db, customer):
        resp = client.get("/customers?q=Jane")
        assert resp.status_code == 200
        body = resp.get_json()
        assert any(c["first_name"] == "Jane" for c in body["data"])



class TestPatchCustomer:
    def test_update_first_name(self, client, db, customer):
        resp = client.patch(f"/customers/{customer.id}", json={"first_name": "Janet"})
        assert resp.status_code == 200
        assert resp.get_json()["customer"]["first_name"] == "Janet"

    def test_update_not_found(self, client, db):
        resp = client.patch(
            "/customers/999999",
            json={"first_name": "X"},
        )
        assert resp.status_code == 404


class TestCustomerAddressFields:
    def test_create_with_address(self, client, db):
        resp = client.post("/customers", json={
            "first_name": "Addr",
            "last_name":  "Test",
            "email":      "addr.test@example.com",
            "address_line1": "123 Main St",
            "address_line2": "Suite 4B",
            "city":          "Springfield",
            "state":         "IL",
            "postal_code":   "62701",
            "country":       "US",
        })
        assert resp.status_code == 201
        c = resp.get_json()["customer"]
        assert c["address_line1"] == "123 Main St"
        assert c["address_line2"] == "Suite 4B"
        assert c["city"] == "Springfield"
        assert c["state"] == "IL"
        assert c["postal_code"] == "62701"
        assert c["country"] == "US"

    def test_create_defaults_country_to_us(self, client, db):
        resp = client.post("/customers", json={
            "first_name": "Default",
            "last_name":  "Country",
            "email":      "default.country@example.com",
        })
        assert resp.status_code == 201
        c = resp.get_json()["customer"]
        assert c["country"] == "US"

    def test_get_returns_address_fields(self, client, db, customer):
        """Address fields are present in GET /customers/{id} response."""
        resp = client.get(f"/customers/{customer.id}")
        assert resp.status_code == 200
        c = resp.get_json()["customer"]
        # All address fields exist in response (may be None for fixture customer)
        for field in ("address_line1", "address_line2", "city", "state", "postal_code", "country"):
            assert field in c

    def test_patch_updates_address(self, client, db, customer):
        resp = client.patch(f"/customers/{customer.id}", json={
            "address_line1": "456 Oak Ave",
            "city":          "Shelbyville",
            "postal_code":   "62565",
        })
        assert resp.status_code == 200
        c = resp.get_json()["customer"]
        assert c["address_line1"] == "456 Oak Ave"
        assert c["city"] == "Shelbyville"
        assert c["postal_code"] == "62565"

    def test_patch_clears_address_with_none(self, client, db):
        """PATCH with null address fields sets them to None."""
        # Create customer with address
        create_resp = client.post("/customers", json={
            "first_name": "Clear",
            "last_name":  "Test",
            "email":      "clear.test@example.com",
            "city":       "Oldtown",
        })
        cid = create_resp.get_json()["customer"]["id"]
        # Clear city
        resp = client.patch(f"/customers/{cid}", json={"city": None})
        assert resp.status_code == 200
        assert resp.get_json()["customer"]["city"] is None
