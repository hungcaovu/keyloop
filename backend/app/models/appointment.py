import enum
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.orm import validates

_BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class AppointmentStatus(str, enum.Enum):
    PENDING   = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    EXPIRED   = "EXPIRED"


class Appointment(db.Model):
    __tablename__ = "appointments"

    id                    = db.Column(_BigInt, primary_key=True, autoincrement=True)
    customer_id           = db.Column(_BigInt, db.ForeignKey("customers.id"), nullable=False)
    booked_by_customer_id = db.Column(_BigInt, db.ForeignKey("customers.id"), nullable=True)
    vehicle_id            = db.Column(_BigInt, db.ForeignKey("vehicles.id"), nullable=False)
    dealership_id         = db.Column(_BigInt, db.ForeignKey("dealerships.id"), nullable=False)
    service_type_id       = db.Column(_BigInt, db.ForeignKey("service_types.id"), nullable=False)
    technician_id         = db.Column(_BigInt, db.ForeignKey("technicians.id"), nullable=False)
    service_bay_id        = db.Column(_BigInt, db.ForeignKey("service_bays.id"), nullable=False)
    scheduled_start       = db.Column(db.DateTime, nullable=False)
    scheduled_end         = db.Column(db.DateTime, nullable=False)
    status                = db.Column(db.String(20), nullable=False, default=AppointmentStatus.PENDING.value)
    expires_at            = db.Column(db.DateTime, nullable=True)   # set only for PENDING holds
    notes                 = db.Column(db.Text, nullable=True)
    created_at            = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at            = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    customer           = db.relationship("Customer", foreign_keys=[customer_id], back_populates="appointments")
    booked_by_customer = db.relationship("Customer", foreign_keys=[booked_by_customer_id], back_populates="booked_appointments")
    vehicle            = db.relationship("Vehicle", back_populates="appointments")
    dealership         = db.relationship("Dealership", back_populates="appointments")
    service_type       = db.relationship("ServiceType", back_populates="appointments")
    technician         = db.relationship("Technician", back_populates="appointments")
    service_bay        = db.relationship("ServiceBay", back_populates="appointments")

    __table_args__ = (
        # Overlap-check indexes: include active PENDING holds alongside CONFIRMED
        db.Index(
            "idx_appointments_technician_time",
            "technician_id", "scheduled_start", "scheduled_end",
            postgresql_where=db.text("status IN ('CONFIRMED', 'PENDING')"),
        ),
        db.Index(
            "idx_appointments_bay_time",
            "service_bay_id", "scheduled_start", "scheduled_end",
            postgresql_where=db.text("status IN ('CONFIRMED', 'PENDING')"),
        ),
        # Fast TTL expiry scan for PENDING cleanup
        db.Index(
            "idx_appointments_pending_expires",
            "expires_at",
            postgresql_where=db.text("status = 'PENDING'"),
        ),
        db.Index(
            "idx_appointments_dealership_status",
            "dealership_id", "status",
        ),
    )

    @validates("status")
    def validate_status(self, key, value):
        valid = {s.value for s in AppointmentStatus}
        if value not in valid:
            raise ValueError(f"Invalid appointment status '{value}'. Must be one of: {sorted(valid)}")
        return value

    def __repr__(self):
        return f"<Appointment {self.id} {self.status} {self.scheduled_start}>"
