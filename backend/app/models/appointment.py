import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class AppointmentStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class Appointment(db.Model):
    __tablename__ = "appointments"

    id                    = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id           = db.Column(db.String(36), db.ForeignKey("customers.id"), nullable=False)
    booked_by_customer_id = db.Column(db.String(36), db.ForeignKey("customers.id"), nullable=True)
    vehicle_id            = db.Column(db.String(36), db.ForeignKey("vehicles.id"), nullable=False)
    dealership_id         = db.Column(db.String(36), db.ForeignKey("dealerships.id"), nullable=False)
    service_type_id       = db.Column(db.String(36), db.ForeignKey("service_types.id"), nullable=False)
    technician_id         = db.Column(db.String(36), db.ForeignKey("technicians.id"), nullable=False)
    service_bay_id        = db.Column(db.String(36), db.ForeignKey("service_bays.id"), nullable=False)
    scheduled_start       = db.Column(db.DateTime, nullable=False)
    scheduled_end         = db.Column(db.DateTime, nullable=False)
    status                = db.Column(db.String(20), nullable=False, default=AppointmentStatus.CONFIRMED.value)
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
        # Core overlap-check indexes (partial on CONFIRMED rows)
        db.Index(
            "idx_appointments_technician_time",
            "technician_id", "scheduled_start", "scheduled_end",
            postgresql_where=db.text("status = 'CONFIRMED'"),
        ),
        db.Index(
            "idx_appointments_bay_time",
            "service_bay_id", "scheduled_start", "scheduled_end",
            postgresql_where=db.text("status = 'CONFIRMED'"),
        ),
        db.Index(
            "idx_appointments_dealership_status",
            "dealership_id", "status",
        ),
    )

    def __repr__(self):
        return f"<Appointment {self.id} {self.status} {self.scheduled_start}>"
