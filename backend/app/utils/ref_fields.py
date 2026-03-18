"""
Custom Marshmallow fields for entity reference IDs.

EntityRefField serialises a BigInt PK to a formatted string (e.g. "C-000001")
and deserialises either that formatted string OR a raw integer back to int.
"""

from __future__ import annotations
from marshmallow import fields as ma_fields, ValidationError
from app.utils.entity_ref import encode, decode


class EntityRefField(ma_fields.Field):
    """
    Bidirectional ref field for one entity type.

    dump (int → str):  1  →  "C-000001"
    load (str|int → int): "C-000001" or 1  →  1
    """

    def __init__(self, entity: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entity = entity

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return encode(self.entity, int(value))

    def _deserialize(self, value, attr, data, **kwargs):
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            parsed = decode(self.entity, value)
            if parsed is not None:
                return parsed
            # Also accept plain numeric string
            if value.isdigit():
                return int(value)
        raise ValidationError(
            f"Invalid {self.entity} ID format: '{value}'."
        )


# Convenience pre-bound instances
def CustomerRef(**kwargs):
    return EntityRefField("customer", **kwargs)

def VehicleRef(**kwargs):
    return EntityRefField("vehicle", **kwargs)

def DealershipRef(**kwargs):
    return EntityRefField("dealership", **kwargs)

def TechnicianRef(**kwargs):
    return EntityRefField("technician", **kwargs)

def ServiceTypeRef(**kwargs):
    return EntityRefField("service_type", **kwargs)

def ServiceBayRef(**kwargs):
    return EntityRefField("service_bay", **kwargs)

def AppointmentRef(**kwargs):
    return EntityRefField("appointment", **kwargs)
