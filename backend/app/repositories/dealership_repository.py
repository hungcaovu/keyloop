from __future__ import annotations
from app.extensions import db
from app.models.dealership import Dealership


class DealershipRepository:
    def get_by_id(self, dealership_id: str) -> Dealership | None:
        return db.session.get(Dealership, dealership_id)

    def search_by_name(self, q: str | None = None, limit: int = 10, after_id: int | None = None) -> list[Dealership]:
        stmt = db.select(Dealership)
        if q:
            stmt = stmt.where(Dealership.name.ilike(f"%{q}%"))
        if after_id is not None:
            stmt = stmt.where(Dealership.id > after_id)
        stmt = stmt.order_by(Dealership.id).limit(limit)
        return list(db.session.execute(stmt).scalars().all())
