from marshmallow import Schema, fields, validate, EXCLUDE
from app.utils.ref_fields import CustomerRef, VehicleRef


class AppointmentCreateSchema(Schema):
    """Input schema for POST /appointments."""
    customer_id           = CustomerRef(required=True)
    vehicle_id            = VehicleRef(required=True)
    dealership_id         = fields.Int(required=True)
    service_type_id       = fields.Int(required=True)
    desired_start         = fields.DateTime(required=True)
    technician_id         = fields.Int(load_default=None)
    booked_by_customer_id = CustomerRef(load_default=None)
    notes                 = fields.Str(load_default=None, validate=validate.Length(max=1000))

    class Meta:
        unknown = EXCLUDE


# ── Nested objects in appointment response ──────────────────────────────────

class _CustomerBriefSchema(Schema):
    id   = CustomerRef()
    name = fields.Method("get_full_name")

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class _VehicleBriefSchema(Schema):
    id    = VehicleRef()
    vin   = fields.Str(allow_none=True)
    year  = fields.Int()
    make  = fields.Str()
    model = fields.Str()


class _DealershipBriefSchema(Schema):
    id   = fields.Int()
    name = fields.Str()


class _ServiceTypeBriefSchema(Schema):
    id               = fields.Int()
    name             = fields.Str()
    duration_minutes = fields.Int()


class _TechnicianBriefSchema(Schema):
    id   = fields.Int()
    name = fields.Method("get_full_name")

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class _ServiceBayBriefSchema(Schema):
    id         = fields.Int()
    bay_number = fields.Str()
    bay_type   = fields.Str()


class AppointmentSchema(Schema):
    """Full appointment response object."""
    id                    = fields.Int(dump_only=True)
    status                = fields.Str()
    customer              = fields.Nested(_CustomerBriefSchema)
    booked_by_customer    = fields.Nested(_CustomerBriefSchema, allow_none=True)
    vehicle               = fields.Nested(_VehicleBriefSchema)
    dealership            = fields.Nested(_DealershipBriefSchema)
    service_type          = fields.Nested(_ServiceTypeBriefSchema)
    technician            = fields.Nested(_TechnicianBriefSchema)
    service_bay           = fields.Nested(_ServiceBayBriefSchema)
    scheduled_start       = fields.DateTime(format='%Y-%m-%dT%H:%M:%SZ')
    scheduled_end         = fields.DateTime(format='%Y-%m-%dT%H:%M:%SZ')
    expires_at            = fields.DateTime(format='%Y-%m-%dT%H:%M:%SZ', allow_none=True)
    notes                 = fields.Str(allow_none=True)
    created_at            = fields.DateTime(format='%Y-%m-%dT%H:%M:%SZ', dump_only=True)

    class Meta:
        unknown = EXCLUDE


class AppointmentResponseSchema(Schema):
    appointment = fields.Nested(AppointmentSchema)


class AppointmentConflictSchema(Schema):
    """409 response when resource is unavailable."""
    error               = fields.Str()
    message             = fields.Str()
    next_available_slot = fields.DateTime(allow_none=True)
