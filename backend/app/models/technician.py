from datetime import datetime, timezone
from app.extensions import db

_BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class TechnicianQualification(db.Model):
    __tablename__ = "technician_qualifications"

    technician_id   = db.Column(_BigInt, db.ForeignKey("technicians.id"), primary_key=True)
    service_type_id = db.Column(_BigInt, db.ForeignKey("service_types.id"), primary_key=True)
    certified_at    = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    # Relationships
    technician   = db.relationship("Technician", back_populates="qualifications")
    service_type = db.relationship("ServiceType", back_populates="qualifications")

    __table_args__ = (
        db.Index("idx_tech_qual_service_type", "service_type_id", "technician_id"),
    )


class Technician(db.Model):
    __tablename__ = "technicians"

    id              = db.Column(_BigInt, primary_key=True, autoincrement=True)
    dealership_id   = db.Column(_BigInt, db.ForeignKey("dealerships.id"), nullable=False)
    first_name      = db.Column(db.String(100), nullable=False)
    last_name       = db.Column(db.String(100), nullable=False)
    employee_number = db.Column(db.String(50), unique=True, nullable=False)
    is_active       = db.Column(db.Boolean, nullable=False, default=True)

    # Relationships
    dealership     = db.relationship("Dealership", back_populates="technicians")
    qualifications = db.relationship(
        "TechnicianQualification", back_populates="technician", lazy="joined"
    )
    appointments   = db.relationship("Appointment", back_populates="technician", lazy="dynamic")

    __table_args__ = (
        db.Index("idx_technicians_dealership_active", "dealership_id",
                 postgresql_where=db.text("is_active = TRUE")),
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Technician {self.full_name} [{self.employee_number}]>"
