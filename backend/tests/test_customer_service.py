"""Unit tests for CustomerService business logic."""

import pytest
from app.services.customer_service import CustomerService
from app.exceptions import NotFoundError, ConflictError


class TestCustomerService:
    def test_create_customer_success(self, db, app):
        with app.app_context():
            svc = CustomerService()
            customer, warning = svc.create("John", "Doe", "john@test.com", "+1-555-9999")
            assert customer.id is not None
            assert customer.first_name == "John"
            assert customer.email == "john@test.com"
            assert warning is None

    def test_create_customer_duplicate_email_raises(self, db, app, customer):
        """POST /customers with duplicate email must return ConflictError."""
        with app.app_context():
            svc = CustomerService()
            with pytest.raises(ConflictError):
                svc.create("Jane", "Other", "jane@test.com", "+1-555-7777")

    def test_create_customer_duplicate_phone_returns_warning(self, db, app, customer):
        """POST /customers with existing phone returns 201 + warning (A14)."""
        with app.app_context():
            svc = CustomerService()
            new_customer, warning = svc.create(
                "James", "Smith", "james.smith@test.com", "+1-555-0101"  # same phone as fixture customer
            )
            assert new_customer is not None
            assert warning is not None
            assert warning["code"] == "DUPLICATE_PHONE"
            assert "existing_customer" in warning

    def test_get_by_id_not_found_raises(self, db, app):
        with app.app_context():
            svc = CustomerService()
            with pytest.raises(NotFoundError):
                svc.get_by_id(999999)

    def test_search_by_phone(self, db, app, customer):
        with app.app_context():
            svc = CustomerService()
            results = svc.search(phone="+1-555-0101")
            assert len(results) == 1
            assert results[0].email == "jane@test.com"

    def test_search_by_name(self, db, app, customer):
        with app.app_context():
            svc = CustomerService()
            results = svc.search(q="Jane")
            assert any(c.first_name == "Jane" for c in results)

    def test_update_customer_success(self, db, app, customer):
        with app.app_context():
            svc = CustomerService()
            updated, warning = svc.update(customer.id, {"first_name": "Jennifer"})
            assert updated.first_name == "Jennifer"
            assert warning is None


class TestVehicleService:
    def test_get_by_vin(self, db, app, vehicle):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            result = svc.get_by_identifier("1HGCM82633A123456")
            assert result.id == vehicle.id

    def test_get_by_id(self, db, app, vehicle):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            result = svc.get_by_identifier(vehicle.id)
            assert result.id == vehicle.id

    def test_invalid_identifier_raises_validation_error(self, db, app):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            from app.exceptions import ValidationError
            svc = VehicleService()
            with pytest.raises(ValidationError):
                svc.get_by_identifier("not-a-valid-identifier")

    def test_create_vehicle_duplicate_vin_raises(self, db, app, customer, vehicle):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            with pytest.raises(ConflictError):
                svc.create(customer.id, "Honda", "Accord", 2022, "1HGCM82633A123456")

    def test_create_vehicle_without_vin(self, db, app, customer):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            v = svc.create(customer.id, "Toyota", "Camry", 2023, vin=None)
            assert v.vin is None
            assert v.make == "Toyota"

    def test_get_by_vehicle_ref(self, db, app, customer):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            v = svc.create(customer.id, "Toyota", "Camry", 2023, vin=None)
            ref = f"V-{v.vehicle_number:06d}"
            found = svc.get_by_identifier(ref)
            assert found.id == v.id

    def test_vehicle_number_auto_increments(self, db, app, customer):
        """Second VIN-less vehicle gets vehicle_number = first + 1."""
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            v1 = svc.create(customer.id, "Toyota", "Camry", 2020, vin=None)
            v2 = svc.create(customer.id, "Honda", "Civic", 2021, vin=None)
            assert v2.vehicle_number == v1.vehicle_number + 1

    def test_vehicle_with_vin_has_no_vehicle_number(self, db, app, customer):
        with app.app_context():
            from app.services.vehicle_service import VehicleService
            svc = VehicleService()
            v = svc.create(customer.id, "Honda", "Accord", 2022, vin="2T1BURHE0JC034521")
            assert v.vehicle_number is None
