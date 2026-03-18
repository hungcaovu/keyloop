from __future__ import annotations
import re
import uuid as uuid_lib
from app.extensions import db
from app.models.vehicle import Vehicle
from app.repositories.vehicle_repository import VehicleRepository
from app.repositories.customer_repository import CustomerRepository
from app.exceptions import NotFoundError, ConflictError, ValidationError
from app.utils.vehicle_ref import is_ref_string, from_ref_string

# VIN: 17 chars, alphanumeric excluding I, O, Q
VIN_PATTERN = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$', re.IGNORECASE)
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class VehicleService:
    def __init__(self):
        self.repo          = VehicleRepository()
        self.customer_repo = CustomerRepository()

    def get_by_identifier(self, identifier: str) -> Vehicle:
        """
        Auto-route lookup by identifier format:
        1. UUID format    → lookup by vehicle.id
        2. 17-char VIN    → lookup by vehicle.vin
        3. V-XXXXXX ref   → lookup by vehicle.vehicle_number
        4. Anything else  → ValidationError (400)
        """
        if UUID_PATTERN.match(identifier):
            vehicle = self.repo.get_by_id(identifier)
            if not vehicle:
                raise NotFoundError(f"Vehicle {identifier} not found.")
            return vehicle

        if VIN_PATTERN.match(identifier):
            vehicle = self.repo.get_by_vin(identifier)
            if not vehicle:
                raise NotFoundError(f"No vehicle with VIN {identifier} found.")
            return vehicle

        if is_ref_string(identifier):
            vehicle_number = from_ref_string(identifier)
            vehicle = self.repo.get_by_vehicle_number(vehicle_number)
            if not vehicle:
                raise NotFoundError(f"No vehicle with reference {identifier.upper()} found.")
            return vehicle

        raise ValidationError(
            "Identifier must be a UUID (vehicle ID), a 17-character VIN, or a V-XXXXXX reference number.",
            field="identifier",
        )

    def list_by_customer(self, customer_id: str) -> list[Vehicle]:
        """Return all vehicles owned by a customer, raising 404 if customer doesn't exist."""
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found.")
        return self.repo.list_by_customer(customer_id)

    def create(self, customer_id: str, make: str, model: str, year: int, vin: str | None = None) -> Vehicle:
        # Validate customer exists
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found.")

        # VIN uniqueness check
        if vin:
            existing = self.repo.get_by_vin(vin)
            if existing:
                raise ConflictError(
                    f"A vehicle with VIN '{vin.upper()}' already exists.",
                    existing=existing,
                )

        vehicle = self.repo.create(customer_id=customer_id, make=make, model=model, year=year, vin=vin)
        db.session.commit()
        return vehicle

    def update(self, vehicle_id: str, data: dict) -> Vehicle:
        vehicle = self.repo.get_by_id(vehicle_id)
        if not vehicle:
            raise NotFoundError(f"Vehicle {vehicle_id} not found.")

        # If updating customer_id, validate new owner exists
        if "customer_id" in data:
            owner = self.customer_repo.get_by_id(data["customer_id"])
            if not owner:
                raise NotFoundError(f"Customer {data['customer_id']} not found.")

        # VIN uniqueness check (skip if same VIN)
        if "vin" in data and data["vin"] and data["vin"].upper() != vehicle.vin:
            existing = self.repo.get_by_vin(data["vin"])
            if existing:
                raise ConflictError(
                    f"A vehicle with VIN '{data['vin'].upper()}' already exists.",
                    existing=existing,
                )

        self.repo.update(vehicle, data)
        db.session.commit()
        return vehicle
