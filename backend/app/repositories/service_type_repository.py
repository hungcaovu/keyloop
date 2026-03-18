from __future__ import annotations
from app.extensions import db
from app.models.service_type import ServiceType


class ServiceTypeRepository:
    def get_by_id(self, service_type_id: str) -> ServiceType | None:
        return db.session.get(ServiceType, service_type_id)

    def list_all(self, limit: int = 20, after_id: int | None = None) -> list[ServiceType]:
        stmt = db.select(ServiceType).order_by(ServiceType.id)
        if after_id is not None:
            stmt = stmt.where(ServiceType.id > after_id)
        stmt = stmt.limit(limit)
        return list(db.session.execute(stmt).scalars().all())

    def search_by_name(self, q: str, limit: int = 20, after_id: int | None = None) -> list[ServiceType]:
        pattern = f"%{q}%"
        stmt = (
            db.select(ServiceType)
            .where(
                db.or_(
                    ServiceType.name.ilike(pattern),
                    ServiceType.description.ilike(pattern),
                )
            )
            .order_by(ServiceType.id)
        )
        if after_id is not None:
            stmt = stmt.where(ServiceType.id > after_id)
        stmt = stmt.limit(limit)
        return list(db.session.execute(stmt).scalars().all())
