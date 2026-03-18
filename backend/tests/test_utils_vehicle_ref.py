"""Unit tests for vehicle_ref utilities."""

import pytest
from app.utils.vehicle_ref import to_ref_string, from_ref_string, is_ref_string


class TestToRefString:
    def test_single_digit(self):
        assert to_ref_string(1) == "V-000001"

    def test_three_digits(self):
        assert to_ref_string(999) == "V-000999"

    def test_six_digits(self):
        assert to_ref_string(999999) == "V-999999"

    def test_over_six_digits(self):
        """Numbers > 999999 are still formatted (no truncation)."""
        assert to_ref_string(1000000) == "V-1000000"

    def test_boundary_zero_padded(self):
        assert to_ref_string(42) == "V-000042"


class TestFromRefString:
    def test_valid_uppercase(self):
        assert from_ref_string("V-000001") == 1

    def test_valid_lowercase(self):
        assert from_ref_string("v-000001") == 1

    def test_strips_leading_zeros(self):
        assert from_ref_string("V-000999") == 999

    def test_large_number(self):
        assert from_ref_string("V-1234567890") == 1234567890

    def test_invalid_no_prefix(self):
        assert from_ref_string("000001") is None

    def test_invalid_wrong_prefix(self):
        assert from_ref_string("X-000001") is None

    def test_invalid_letters_in_number(self):
        assert from_ref_string("V-00000A") is None

    def test_empty_string(self):
        assert from_ref_string("") is None

    def test_vin_is_not_ref(self):
        assert from_ref_string("1HGCM82633A123456") is None

    def test_roundtrip(self):
        """to_ref_string → from_ref_string is lossless."""
        for n in [1, 42, 999, 100000]:
            assert from_ref_string(to_ref_string(n)) == n


class TestIsRefString:
    def test_valid(self):
        assert is_ref_string("V-000001") is True

    def test_valid_lowercase(self):
        assert is_ref_string("v-000001") is True

    def test_invalid_dashed_string(self):
        assert is_ref_string("00000000-0000-0000-0000-000000000000") is False

    def test_invalid_vin(self):
        assert is_ref_string("1HGCM82633A123456") is False

    def test_invalid_random(self):
        assert is_ref_string("not-a-ref") is False

    def test_empty(self):
        assert is_ref_string("") is False
