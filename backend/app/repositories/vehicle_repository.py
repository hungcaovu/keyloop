from __future__ import annotations
from sqlalchemy import func

from app.extensions import db
from app.models.vehicle import Vehicle


class VehicleRepository:
    def get_by_id(self, vehicle_id: str) -> Vehicle | None:
        return db.session.get(Vehicle, vehicle_id)

    def get_by_vin(self, vin: str) -> Vehicle | None:
        return db.session.execute(
            db.select(Vehicle).where(Vehicle.vin == vin.upper())
        ).scalar_one_or_none()

    def list_by_customer(self, customer_id: str) -> list[Vehicle]:
        return list(
            db.session.execute(
                db.select(Vehicle)
                .where(Vehicle.customer_id == customer_id)
                .order_by(Vehicle.created_at.asc())
            ).scalars().all()
        )

    def get_by_vehicle_number(self, vehicle_number: int) -> Vehicle | None:
        return db.session.execute(
            db.select(Vehicle).where(Vehicle.vehicle_number == vehicle_number)
        ).scalar_one_or_none()

    def create(self, customer_id: str, make: str, model: str, year: int, vin: str | None = None) -> Vehicle:
        # Auto-assign vehicle_number for vehicles without VIN
        vehicle_number = None
        if not vin:
            max_num = db.session.execute(
                db.select(func.max(Vehicle.vehicle_number))
            ).scalar()
            vehicle_number = (max_num or 0) + 1

        vehicle = Vehicle(
            customer_id=customer_id,
            vehicle_number=vehicle_number,
            make=make,
            model=model,
            year=year,
            vin=vin.upper() if vin else None,
        )
        db.session.add(vehicle)
        db.session.flush()
        return vehicle

    def update(self, vehicle: Vehicle, data: dict) -> Vehicle:
        allowed = {"customer_id", "make", "model", "year", "vin"}
        for key, value in data.items():
            if key in allowed:
                if key == "vin" and value:
                    value = value.upper()
                setattr(vehicle, key, value)
        db.session.flush()
        return vehicle
