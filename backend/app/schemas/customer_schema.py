from marshmallow import Schema, fields, validate, EXCLUDE
from app.utils.ref_fields import CustomerRef


class CustomerSchema(Schema):
    """Output schema — full customer object."""
    id            = CustomerRef(dump_only=True)
    first_name    = fields.Str()
    last_name     = fields.Str()
    email         = fields.Email()
    phone         = fields.Str(allow_none=True)
    address_line1 = fields.Str(allow_none=True)
    address_line2 = fields.Str(allow_none=True)
    city          = fields.Str(allow_none=True)
    state         = fields.Str(allow_none=True)
    postal_code   = fields.Str(allow_none=True)
    country       = fields.Str(allow_none=True)
    created_at    = fields.DateTime(dump_only=True)

    class Meta:
        unknown = EXCLUDE


class CustomerCreateSchema(Schema):
    """Input schema for POST /customers."""
    first_name    = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    last_name     = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    email         = fields.Email(required=True)
    phone         = fields.Str(load_default=None, validate=validate.Length(max=30))
    address_line1 = fields.Str(load_default=None, validate=validate.Length(max=255))
    address_line2 = fields.Str(load_default=None, validate=validate.Length(max=255))
    city          = fields.Str(load_default=None, validate=validate.Length(max=100))
    state         = fields.Str(load_default=None, validate=validate.Length(max=100))
    postal_code   = fields.Str(load_default=None, validate=validate.Length(max=20))
    country       = fields.Str(load_default="US", validate=validate.Length(max=100))

    class Meta:
        unknown = EXCLUDE


class CustomerUpdateSchema(Schema):
    """Input schema for PATCH /customers/{id}."""
    first_name    = fields.Str(validate=validate.Length(min=1, max=100))
    last_name     = fields.Str(validate=validate.Length(min=1, max=100))
    email         = fields.Email()
    phone         = fields.Str(allow_none=True, validate=validate.Length(max=30))
    address_line1 = fields.Str(allow_none=True, validate=validate.Length(max=255))
    address_line2 = fields.Str(allow_none=True, validate=validate.Length(max=255))
    city          = fields.Str(allow_none=True, validate=validate.Length(max=100))
    state         = fields.Str(allow_none=True, validate=validate.Length(max=100))
    postal_code   = fields.Str(allow_none=True, validate=validate.Length(max=20))
    country       = fields.Str(allow_none=True, validate=validate.Length(max=100))

    class Meta:
        unknown = EXCLUDE


class DuplicatePhoneWarningSchema(Schema):
    code              = fields.Str()
    message           = fields.Str()
    existing_customer = fields.Dict()


class CustomerResponseSchema(Schema):
    """Envelope schema for customer endpoints (may include optional warning)."""
    customer = fields.Nested(CustomerSchema)
    warning  = fields.Nested(DuplicatePhoneWarningSchema, allow_none=True, load_default=None)

    class Meta:
        unknown = EXCLUDE


class CustomerListSchema(Schema):
    data = fields.List(fields.Nested(CustomerSchema))
