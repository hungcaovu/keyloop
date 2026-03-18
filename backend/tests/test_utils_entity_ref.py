"""Unit tests for entity_ref utilities (encode / decode / is_ref / parse_id)."""

import pytest
from app.utils.entity_ref import encode, decode, is_ref, parse_id


class TestEncode:
    def test_customer(self):
        assert encode("customer", 1) == "C-000001"

    def test_vehicle(self):
        assert encode("vehicle", 2) == "VH-000002"

    def test_dealership(self):
        assert encode("dealership", 3) == "D-000003"

    def test_technician(self):
        assert encode("technician", 4) == "T-000004"

    def test_service_type(self):
        assert encode("service_type", 5) == "ST-000005"

    def test_service_bay(self):
        assert encode("service_bay", 6) == "SB-000006"

    def test_appointment(self):
        assert encode("appointment", 7) == "APT-000007"

    def test_large_id_expands_width(self):
        """IDs > 6 digits should not be truncated."""
        assert encode("customer", 1234567) == "C-1234567"

    def test_roundtrip(self):
        for entity in ("customer", "vehicle", "dealership", "technician",
                       "service_type", "service_bay", "appointment"):
            for pk in (1, 42, 999999):
                assert decode(entity, encode(entity, pk)) == pk


class TestDecode:
    def test_customer_uppercase(self):
        assert decode("customer", "C-000001") == 1

    def test_customer_lowercase(self):
        assert decode("customer", "c-000001") == 1

    def test_vehicle(self):
        assert decode("vehicle", "VH-000042") == 42

    def test_strips_leading_zeros(self):
        assert decode("customer", "C-000999") == 999

    def test_wrong_prefix_returns_none(self):
        assert decode("customer", "VH-000001") is None

    def test_non_ref_string_returns_none(self):
        assert decode("customer", "not-a-ref") is None

    def test_empty_returns_none(self):
        assert decode("customer", "") is None


class TestIsRef:
    def test_valid_customer_ref(self):
        assert is_ref("customer", "C-000001") is True

    def test_valid_vehicle_ref(self):
        assert is_ref("vehicle", "VH-000001") is True

    def test_case_insensitive(self):
        assert is_ref("customer", "c-000001") is True

    def test_wrong_entity_prefix(self):
        assert is_ref("customer", "VH-000001") is False

    def test_plain_integer_is_not_ref(self):
        assert is_ref("customer", "1") is False

    def test_random_string(self):
        assert is_ref("customer", "not-a-ref") is False


class TestParseId:
    def test_plain_integer_string(self):
        assert parse_id("customer", "1") == 1

    def test_ref_string(self):
        assert parse_id("customer", "C-000001") == 1

    def test_ref_string_case_insensitive(self):
        assert parse_id("customer", "c-000042") == 42

    def test_raw_int(self):
        assert parse_id("customer", 99) == 99

    def test_invalid_returns_none(self):
        assert parse_id("customer", "not-a-ref") is None

    def test_wrong_prefix_returns_none(self):
        assert parse_id("customer", "VH-000001") is None


class TestCustomerRefLookupRoute:
    """Integration tests: GET /customers/{C-XXXXXX} should resolve to the correct customer."""

    def test_get_by_ref_string(self, client, db, customer):
        ref = encode("customer", customer.id)          # e.g. "C-000001"
        resp = client.get(f"/customers/{ref}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["customer"]["id"] == ref

    def test_get_by_ref_string_case_insensitive(self, client, db, customer):
        ref = encode("customer", customer.id).lower()  # e.g. "c-000001"
        resp = client.get(f"/customers/{ref}")
        assert resp.status_code == 200

    def test_patch_by_ref_string(self, client, db, customer):
        ref = encode("customer", customer.id)
        resp = client.patch(f"/customers/{ref}", json={"first_name": "Updated"})
        assert resp.status_code == 200
        assert resp.get_json()["customer"]["first_name"] == "Updated"
