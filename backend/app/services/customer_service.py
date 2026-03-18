from __future__ import annotations
from app.extensions import db
from app.models.customer import Customer
from app.repositories.customer_repository import CustomerRepository
from app.exceptions import NotFoundError, ConflictError


class CustomerService:
    def __init__(self):
        self.repo = CustomerRepository()

    def search(self, phone: str | None = None, q: str | None = None, limit: int = 10, after_id: int | None = None) -> list[Customer]:
        if phone:
            return self.repo.get_by_phone(phone)
        if q:
            return self.repo.search_by_name(q, limit=limit, after_id=after_id)
        return []

    def get_by_id(self, customer_id: str) -> Customer:
        customer = self.repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found.")
        return customer

    def create(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None = None,
        address_line1: str | None = None,
        address_line2: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ):
        """
        Create a new customer. If the email already exists, raise ConflictError.
        If the phone already belongs to another customer, return (customer, warning).
        """
        existing_email = self.repo.get_by_email(email)
        if existing_email:
            raise ConflictError(
                f"A customer with email '{email}' already exists.",
                existing=existing_email,
            )

        customer = self.repo.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        )
        db.session.commit()

        warning = None
        if phone:
            duplicate = self.repo.find_duplicate_phone(phone, exclude_id=customer.id)
            if duplicate:
                warning = {
                    "code": "DUPLICATE_PHONE",
                    "message": "This phone number is already associated with another customer.",
                    "existing_customer": {
                        "id": duplicate.id,
                        "first_name": duplicate.first_name,
                        "last_name": duplicate.last_name,
                    },
                }

        return customer, warning

    def update(self, customer_id: str, data: dict):
        customer = self.get_by_id(customer_id)

        if "email" in data and data["email"] != customer.email:
            existing_email = self.repo.get_by_email(data["email"])
            if existing_email:
                raise ConflictError(
                    f"A customer with email '{data['email']}' already exists.",
                    existing=existing_email,
                )

        self.repo.update(customer, data)
        db.session.commit()

        warning = None
        new_phone = data.get("phone")
        if new_phone:
            duplicate = self.repo.find_duplicate_phone(new_phone, exclude_id=customer.id)
            if duplicate:
                warning = {
                    "code": "DUPLICATE_PHONE",
                    "message": "This phone number is already associated with another customer.",
                    "existing_customer": {
                        "id": duplicate.id,
                        "first_name": duplicate.first_name,
                        "last_name": duplicate.last_name,
                    },
                }

        return customer, warning
