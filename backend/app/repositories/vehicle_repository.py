from __future__ import annotations
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError as SAIntegrityError

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
        if vin:
            vehicle = Vehicle(
                customer_id=customer_id, vehicle_number=None,
                make=make, model=model, year=year, vin=vin.upper(),
            )
            db.session.add(vehicle)
            db.session.flush()
            return vehicle

        # No VIN — auto-assign vehicle_number. Retry up to 3 times on concurrent conflict.
        for _attempt in range(3):
            max_num = db.session.execute(
                db.select(func.max(Vehicle.vehicle_number))
            ).scalar()
            vehicle = Vehicle(
                customer_id=customer_id, vehicle_number=(max_num or 0) + 1,
                make=make, model=model, year=year, vin=None,
            )
            db.session.add(vehicle)
            sp = db.session.begin_nested()
            try:
                db.session.flush()
                return vehicle
            except SAIntegrityError:
                sp.rollback()
                db.session.expunge(vehicle)
        raise RuntimeError("Could not auto-assign vehicle reference number. Please try again.")

    def update(self, vehicle: Vehicle, data: dict) -> Vehicle:
        allowed = {"customer_id", "make", "model", "year", "vin"}
        for key, value in data.items():
            if key in allowed:
                if key == "vin" and value:
                    value = value.upper()
                setattr(vehicle, key, value)
        db.session.flush()
        return vehicle
