from marshmallow import Schema, fields, EXCLUDE


class DealershipSchema(Schema):
    id       = fields.Str(dump_only=True)
    name     = fields.Str()
    address  = fields.Str(allow_none=True)
    city     = fields.Str()
    state    = fields.Str()
    timezone = fields.Str()

    class Meta:
        unknown = EXCLUDE


class DealershipListSchema(Schema):
    data = fields.List(fields.Nested(DealershipSchema))
