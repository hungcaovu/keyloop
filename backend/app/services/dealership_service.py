from __future__ import annotations
from app.models.dealership import Dealership
from app.repositories.dealership_repository import DealershipRepository
from app.exceptions import NotFoundError


class DealershipService:
    def __init__(self):
        self.repo = DealershipRepository()

    def search(self, q: str | None = None, limit: int = 10, after_id: int | None = None) -> list[Dealership]:
        return self.repo.search_by_name(q=q, limit=limit, after_id=after_id)

    def get_by_id(self, dealership_id: str) -> Dealership:
        dealership = self.repo.get_by_id(dealership_id)
        if not dealership:
            raise NotFoundError(f"Dealership {dealership_id} not found.")
        return dealership
