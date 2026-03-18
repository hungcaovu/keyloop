from marshmallow import Schema, fields, validate, EXCLUDE


# ── Query parameter schemas ─────────────────────────────────────────────────

class CalendarQuerySchema(Schema):
    service_type_id = fields.Int(required=True)
    from_date       = fields.Date(load_default=None)
    days            = fields.Int(load_default=15, validate=validate.Range(min=1, max=30))
    technician_id   = fields.Int(load_default=None)

    class Meta:
        unknown = EXCLUDE


class SpotCheckQuerySchema(Schema):
    service_type_id = fields.Int(required=True)
    desired_start   = fields.DateTime(required=True)
    technician_id   = fields.Int(load_default=None)

    class Meta:
        unknown = EXCLUDE


class AvailabilityQuerySchema(Schema):
    """
    Combined query schema for GET /dealerships/{id}/availability.
    Mode is determined by presence of desired_start:
      - desired_start present → Spot Check mode
      - desired_start absent  → Calendar mode
    """
    service_type_id = fields.Int(required=True)
    desired_start   = fields.DateTime(load_default=None)
    from_date       = fields.Date(load_default=None)
    days            = fields.Int(load_default=15, validate=validate.Range(min=1, max=30))
    technician_id   = fields.Int(load_default=None)

    class Meta:
        unknown = EXCLUDE


# ── Response schemas ────────────────────────────────────────────────────────

class TimeSlotSchema(Schema):
    start            = fields.DateTime()
    end              = fields.DateTime()
    technician_count = fields.Int()


class DaySlotSchema(Schema):
    date            = fields.Str()
    available_times = fields.List(fields.Nested(TimeSlotSchema))


class FilteredTechnicianSchema(Schema):
    id   = fields.Int()
    name = fields.Str()


class ServiceTypeInfoSchema(Schema):
    name             = fields.Str()
    duration_minutes = fields.Int()


class CalendarResponseSchema(Schema):
    service_type        = fields.Nested(ServiceTypeInfoSchema)
    from_date           = fields.Str()
    to_date             = fields.Str()
    filtered_technician = fields.Nested(FilteredTechnicianSchema, allow_none=True)
    slots               = fields.List(fields.Nested(DaySlotSchema))


class SpotCheckTechnicianSchema(Schema):
    id              = fields.Int()
    name            = fields.Method("get_full_name")
    employee_number = fields.Str()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class SpotCheckResponseSchema(Schema):
    desired_start         = fields.DateTime(allow_none=True)
    desired_end           = fields.DateTime(allow_none=True)
    available             = fields.Bool()
    available_technicians = fields.List(fields.Nested(SpotCheckTechnicianSchema))
    bay_available         = fields.Bool()
    next_available_slot   = fields.DateTime(allow_none=True)
