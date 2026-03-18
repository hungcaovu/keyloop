from marshmallow import Schema, fields, validate, EXCLUDE
from datetime import date as date_type


class VehicleSchema(Schema):
    id             = fields.Str(dump_only=True)
    customer_id    = fields.Str()
    vehicle_number = fields.Int(dump_only=True, allow_none=True)
    vehicle_ref    = fields.Method("get_vehicle_ref", dump_only=True)
    vin            = fields.Str(allow_none=True)
    make           = fields.Str()
    model          = fields.Str()
    year           = fields.Int()
    created_at     = fields.DateTime(dump_only=True)

    def get_vehicle_ref(self, obj):
        """Return 'V-000001' for vehicles without VIN, None for vehicles with VIN."""
        if obj.vehicle_number is not None:
            from app.utils.vehicle_ref import to_ref_string
            return to_ref_string(obj.vehicle_number)
        return None

    class Meta:
        unknown = EXCLUDE


class VehicleCreateSchema(Schema):
    customer_id = fields.Str(required=True)
    vin         = fields.Str(load_default=None, validate=validate.Length(equal=17), allow_none=True)
    make        = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    model       = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    year        = fields.Int(
        required=True,
        validate=validate.Range(min=1900, max=date_type.today().year + 2),
    )

    class Meta:
        unknown = EXCLUDE


class VehicleUpdateSchema(Schema):
    customer_id = fields.Str()
    make        = fields.Str(validate=validate.Length(min=1, max=100))
    model       = fields.Str(validate=validate.Length(min=1, max=100))
    year        = fields.Int(validate=validate.Range(min=1900, max=date_type.today().year + 2))
    vin         = fields.Str(allow_none=True, validate=validate.Length(equal=17))

    class Meta:
        unknown = EXCLUDE


class VehicleResponseSchema(Schema):
    vehicle = fields.Nested(VehicleSchema)
