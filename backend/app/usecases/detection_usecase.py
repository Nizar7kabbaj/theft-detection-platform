from __future__ import annotations

from datetime import datetime, timezone
from app.core.errors import NotFoundError
from app.repositories.detection_repository import DetectionRepository
from app.schemas.detection import DetectionCreate, DetectionResponse


class DetectionUseCase:
    def __init__(self, repo: DetectionRepository) -> None:
        self._repo = repo

    async def create(self, payload: DetectionCreate) -> DetectionResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        created = await self._repo.create(doc)
        return DetectionResponse.model_validate(created)

    async def list(self, limit: int = 50, skip: int = 0) -> list[DetectionResponse]:
        docs = await self._repo.list_recent(limit=limit, skip=skip)
        return [DetectionResponse.model_validate(d) for d in docs]

    async def list_by_session(self, session_id: int) -> list[DetectionResponse]:
        docs = await self._repo.list_by_session(session_id)
        return [DetectionResponse.model_validate(d) for d in docs]

    async def delete(self, detection_id: str) -> None:
        deleted = await self._repo.delete(detection_id)
        if not deleted:
            raise NotFoundError(f"detection {detection_id} not found")
