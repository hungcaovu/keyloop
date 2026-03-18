from __future__ import annotations
from sqlalchemy import or_, func
from app.extensions import db
from app.models.customer import Customer


class CustomerRepository:
    def get_by_id(self, customer_id: str) -> Customer | None:
        return db.session.get(Customer, customer_id)

    def get_by_email(self, email: str) -> Customer | None:
        return db.session.execute(
            db.select(Customer).where(func.lower(Customer.email) == func.lower(email))
        ).scalar_one_or_none()

    def get_by_phone(self, phone: str) -> list[Customer]:
        return list(
            db.session.execute(
                db.select(Customer).where(Customer.phone == phone)
            ).scalars().all()
        )

    def search_by_name(self, q: str, limit: int = 10) -> list[Customer]:
        pattern = f"%{q}%"
        return list(
            db.session.execute(
                db.select(Customer)
                .where(
                    or_(
                        Customer.first_name.ilike(pattern),
                        Customer.last_name.ilike(pattern),
                        func.concat(Customer.first_name, " ", Customer.last_name).ilike(pattern),
                    )
                )
                .limit(limit)
            ).scalars().all()
        )

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
    ) -> Customer:
        customer = Customer(
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
        db.session.add(customer)
        db.session.flush()
        return customer

    def update(self, customer: Customer, data: dict) -> Customer:
        allowed = {
            "first_name", "last_name", "email", "phone",
            "address_line1", "address_line2", "city", "state", "postal_code", "country",
        }
        for key, value in data.items():
            if key in allowed:
                setattr(customer, key, value)
        db.session.flush()
        return customer

    def find_duplicate_phone(self, phone: str, exclude_id: str | None = None) -> Customer | None:
        """Return the first OTHER customer sharing the same phone number."""
        q = db.select(Customer).where(Customer.phone == phone)
        if exclude_id:
            q = q.where(Customer.id != exclude_id)
        return db.session.execute(q).scalars().first()
