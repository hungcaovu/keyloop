from marshmallow import Schema, fields, validate, EXCLUDE


class AppointmentCreateSchema(Schema):
    """Input schema for POST /appointments."""
    customer_id           = fields.Str(required=True)
    vehicle_id            = fields.Str(required=True)
    dealership_id         = fields.Str(required=True)
    service_type_id       = fields.Str(required=True)
    desired_start         = fields.DateTime(required=True)
    technician_id         = fields.Str(load_default=None)
    booked_by_customer_id = fields.Str(load_default=None)
    notes                 = fields.Str(load_default=None, validate=validate.Length(max=1000))

    class Meta:
        unknown = EXCLUDE


# ── Nested objects in appointment response ──────────────────────────────────

class _CustomerBriefSchema(Schema):
    id   = fields.Str()
    name = fields.Method("get_full_name")

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class _VehicleBriefSchema(Schema):
    id    = fields.Str()
    vin   = fields.Str(allow_none=True)
    year  = fields.Int()
    make  = fields.Str()
    model = fields.Str()


class _DealershipBriefSchema(Schema):
    id   = fields.Str()
    name = fields.Str()


class _ServiceTypeBriefSchema(Schema):
    id               = fields.Str()
    name             = fields.Str()
    duration_minutes = fields.Int()


class _TechnicianBriefSchema(Schema):
    id   = fields.Str()
    name = fields.Method("get_full_name")

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class _ServiceBayBriefSchema(Schema):
    id         = fields.Str()
    bay_number = fields.Str()
    bay_type   = fields.Str()


class AppointmentSchema(Schema):
    """Full appointment response object."""
    id                    = fields.Str(dump_only=True)
    status                = fields.Str()
    customer              = fields.Nested(_CustomerBriefSchema)
    booked_by_customer    = fields.Nested(_CustomerBriefSchema, allow_none=True)
    vehicle               = fields.Nested(_VehicleBriefSchema)
    dealership            = fields.Nested(_DealershipBriefSchema)
    service_type          = fields.Nested(_ServiceTypeBriefSchema)
    technician            = fields.Nested(_TechnicianBriefSchema)
    service_bay           = fields.Nested(_ServiceBayBriefSchema)
    scheduled_start       = fields.DateTime()
    scheduled_end         = fields.DateTime()
    notes                 = fields.Str(allow_none=True)
    created_at            = fields.DateTime(dump_only=True)

    class Meta:
        unknown = EXCLUDE


class AppointmentResponseSchema(Schema):
    appointment = fields.Nested(AppointmentSchema)


class AppointmentConflictSchema(Schema):
    """409 response when resource is unavailable."""
    error               = fields.Str()
    message             = fields.Str()
    next_available_slot = fields.DateTime(allow_none=True)
