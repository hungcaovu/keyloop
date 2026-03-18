import uuid
from datetime import datetime, timezone
from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id           = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name   = db.Column(db.String(100), nullable=False)
    last_name    = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(255), unique=True, nullable=False)
    phone        = db.Column(db.String(30), nullable=True, index=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city          = db.Column(db.String(100), nullable=True)
    state         = db.Column(db.String(100), nullable=True)
    postal_code   = db.Column(db.String(20), nullable=True)
    country       = db.Column(db.String(100), nullable=True, default="US")
    created_at   = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    vehicles     = db.relationship("Vehicle", back_populates="owner", lazy="dynamic")
    appointments = db.relationship(
        "Appointment",
        foreign_keys="Appointment.customer_id",
        back_populates="customer",
        lazy="dynamic",
    )
    booked_appointments = db.relationship(
        "Appointment",
        foreign_keys="Appointment.booked_by_customer_id",
        back_populates="booked_by_customer",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name}>"
