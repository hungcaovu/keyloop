from app.extensions import db


class ServiceType(db.Model):
    __tablename__ = "service_types"

    id                = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name              = db.Column(db.String(255), nullable=False)
    description       = db.Column(db.Text, nullable=True)
    duration_minutes  = db.Column(db.Integer, nullable=False)
    required_bay_type = db.Column(db.String(50), nullable=False)

    # Relationships
    qualifications = db.relationship(
        "TechnicianQualification", back_populates="service_type", lazy="dynamic"
    )
    appointments = db.relationship("Appointment", back_populates="service_type", lazy="dynamic")

    def __repr__(self):
        return f"<ServiceType {self.name} ({self.duration_minutes}min)>"
