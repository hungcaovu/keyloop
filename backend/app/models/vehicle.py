from datetime import datetime, timezone
from app.extensions import db

_BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    id             = db.Column(_BigInt, primary_key=True, autoincrement=True)
    customer_id    = db.Column(_BigInt, db.ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_number = db.Column(_BigInt, unique=True, nullable=True, index=True)
    vin            = db.Column(db.String(17), unique=True, nullable=True)
    make           = db.Column(db.String(100), nullable=False)
    model          = db.Column(db.String(100), nullable=False)
    year           = db.Column(db.Integer, nullable=False)
    created_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    owner        = db.relationship("Customer", back_populates="vehicles")
    appointments = db.relationship("Appointment", back_populates="vehicle", lazy="dynamic")

    def __repr__(self):
        return f"<Vehicle {self.year} {self.make} {self.model} VIN={self.vin}>"
