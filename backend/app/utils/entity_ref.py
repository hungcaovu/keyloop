"""
Entity reference ID utilities.

All primary keys are BigInteger auto-increment. For human readability the API
encodes them as prefixed zero-padded strings:

  Customer     id=1   → "C-000001"
  Vehicle      id=2   → "VH-000002"
  Dealership   id=3   → "D-000003"
  Technician   id=4   → "T-000004"
  ServiceType  id=5   → "ST-000005"
  ServiceBay   id=6   → "SB-000006"
  Appointment  id=7   → "APT-000007"

Note: "V-XXXXXX" is reserved for vehicle_number (VIN-less surrogate ref).
"""

from __future__ import annotations
import re

# (prefix, compiled pattern)
_SPECS: dict[str, tuple[str, re.Pattern]] = {}


def _register(entity: str, prefix: str) -> None:
    pattern = re.compile(
        rf'^{re.escape(prefix)}(\d{{1,15}})$',
        re.IGNORECASE,
    )
    _SPECS[entity] = (prefix, pattern)


_register("customer",    "C-")
_register("vehicle",     "VH-")
_register("dealership",  "D-")
_register("technician",  "T-")
_register("service_type", "ST-")
_register("service_bay", "SB-")
_register("appointment", "APT-")


def encode(entity: str, pk: int) -> str:
    """Encode a BigInt PK to its formatted reference string."""
    prefix, _ = _SPECS[entity]
    width = max(6, len(str(pk)))
    return f"{prefix}{pk:0{width}d}"


def decode(entity: str, ref: str) -> int | None:
    """Parse a formatted reference string back to its integer PK.
    Returns None if the string does not match the expected format.
    """
    _, pattern = _SPECS[entity]
    m = pattern.match(ref)
    if m:
        return int(m.group(1))
    return None


def is_ref(entity: str, value: str) -> bool:
    _, pattern = _SPECS[entity]
    return bool(pattern.match(value))


def parse_id(entity: str, value: str) -> int | None:
    """
    Parse a route path parameter to an integer PK.
    Accepts:  "C-000001"  →  1
              "1"         →  1
              123         →  123
    Returns None if the value cannot be resolved (caller should return 404).
    """
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.isdigit():
            return int(value)
        parsed = decode(entity, value)
        if parsed is not None:
            return parsed
    return None
