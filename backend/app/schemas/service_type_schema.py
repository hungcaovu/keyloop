from marshmallow import Schema, fields, EXCLUDE


class ServiceTypeSchema(Schema):
    id                = fields.Int(dump_only=True)
    name              = fields.Str()
    description       = fields.Str(allow_none=True)
    duration_minutes  = fields.Int()
    required_bay_type = fields.Str()

    class Meta:
        unknown = EXCLUDE


class ServiceTypeListSchema(Schema):
    data = fields.List(fields.Nested(ServiceTypeSchema))
