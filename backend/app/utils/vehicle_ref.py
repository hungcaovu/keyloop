from __future__ import annotations
"""
Vehicle reference number utilities.

For vehicles without a VIN, `vehicle_number` (auto-increment BigInt) provides
a human-readable reference. It is stored as an integer in the DB for performance
(8-byte integer index vs 36-char UUID string index).

Encoding: zero-padded 6-digit string prefixed with "V-".
  vehicle_number=1   → "V-000001"
  vehicle_number=999 → "V-000999"

Lookup path in GET /vehicles/{identifier}:
  1. UUID pattern           → lookup by vehicle.id
  2. 17-char VIN            → lookup by vehicle.vin
  3. V-XXXXXX pattern       → lookup by vehicle.vehicle_number
  4. Anything else          → 400 Bad Request
"""

import re

REF_PREFIX = "V-"
REF_PATTERN = re.compile(r'^V-(\d{1,10})$', re.IGNORECASE)


def to_ref_string(vehicle_number: int) -> str:
    """Convert integer vehicle_number to display format: 1 → 'V-000001'."""
    return f"{REF_PREFIX}{vehicle_number:06d}"


def from_ref_string(ref: str) -> int | None:
    """Parse 'V-000001' → 1. Returns None if the string is not a valid ref."""
    m = REF_PATTERN.match(ref.upper())
    if m:
        return int(m.group(1))
    return None


def is_ref_string(identifier: str) -> bool:
    return bool(REF_PATTERN.match(identifier.upper()))
