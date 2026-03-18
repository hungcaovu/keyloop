import uuid
from app.extensions import db


class ServiceBay(db.Model):
    __tablename__ = "service_bays"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dealership_id = db.Column(db.String(36), db.ForeignKey("dealerships.id"), nullable=False)
    bay_number    = db.Column(db.String(20), nullable=False)
    bay_type      = db.Column(db.String(50), nullable=False)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)

    # Relationships
    dealership   = db.relationship("Dealership", back_populates="service_bays")
    appointments = db.relationship("Appointment", back_populates="service_bay", lazy="dynamic")

    __table_args__ = (
        db.Index(
            "idx_bays_dealership_type",
            "dealership_id",
            "bay_type",
            postgresql_where=db.text("is_active = TRUE"),
        ),
    )

    def __repr__(self):
        return f"<ServiceBay {self.bay_number} ({self.bay_type})>"
