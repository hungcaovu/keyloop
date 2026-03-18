import uuid
from app.extensions import db


class Dealership(db.Model):
    __tablename__ = "dealerships"

    id       = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name     = db.Column(db.String(255), nullable=False, index=True)
    address  = db.Column(db.String(500), nullable=True)
    city     = db.Column(db.String(100), nullable=False)
    state    = db.Column(db.String(100), nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default="UTC")

    # Relationships
    technicians  = db.relationship("Technician", back_populates="dealership", lazy="dynamic")
    service_bays = db.relationship("ServiceBay", back_populates="dealership", lazy="dynamic")
    appointments = db.relationship("Appointment", back_populates="dealership", lazy="dynamic")

    def __repr__(self):
        return f"<Dealership {self.name}>"
