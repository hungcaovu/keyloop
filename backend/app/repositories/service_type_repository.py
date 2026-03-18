from __future__ import annotations
from app.extensions import db
from app.models.service_type import ServiceType


class ServiceTypeRepository:
    def get_by_id(self, service_type_id: str) -> ServiceType | None:
        return db.session.get(ServiceType, service_type_id)

    def list_all(self) -> list[ServiceType]:
        return list(db.session.execute(db.select(ServiceType).order_by(ServiceType.name)).scalars().all())

    def search_by_name(self, q: str, limit: int = 20) -> list[ServiceType]:
        pattern = f"%{q}%"
        return list(
            db.session.execute(
                db.select(ServiceType)
                .where(
                    db.or_(
                        ServiceType.name.ilike(pattern),
                        ServiceType.description.ilike(pattern),
                    )
                )
                .order_by(ServiceType.name)
                .limit(limit)
            ).scalars().all()
        )
