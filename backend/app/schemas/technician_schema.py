from marshmallow import Schema, fields, EXCLUDE


class TechnicianSchema(Schema):
    id              = fields.Str(dump_only=True)
    first_name      = fields.Str()
    last_name       = fields.Str()
    name            = fields.Method("get_full_name")
    employee_number = fields.Str()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    class Meta:
        unknown = EXCLUDE


class TechnicianListSchema(Schema):
    data = fields.List(fields.Nested(TechnicianSchema))
