from __future__ import annotations

from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from app.core.errors import ConflictError, NotFoundError
from app.repositories.camera_repository import CameraRepository
from app.schemas.camera import CameraCreate, CameraResponse


class CameraUseCase:
    def __init__(self, repo: CameraRepository) -> None:
        self._repo = repo

    async def create(self, payload: CameraCreate) -> CameraResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        try:
            created = await self._repo.create(doc)
        except DuplicateKeyError as exc:
            raise ConflictError(f"camera with name {payload.name} already exists") from exc
        return CameraResponse.model_validate(created)

    async def list(self) -> list[CameraResponse]:
        docs = await self._repo.list(limit=200)
        return [CameraResponse.model_validate(d) for d in docs]

    async def get(self, camera_id: str) -> CameraResponse:
        doc = await self._repo.get(camera_id)
        if doc is None:
            raise NotFoundError(f"camera {camera_id} not found")
        return CameraResponse.model_validate(doc)

    async def delete(self, camera_id: str) -> None:
        deleted = await self._repo.delete(camera_id)
        if not deleted:
            raise NotFoundError(f"camera {camera_id} not found")
