from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import NotFoundError
from app.repositories.detection_repository import DetectionRepository
from app.schemas.detection import DetectionCreate, DetectionResponse
from app.services.inference_service import InferenceClient


class DetectionUseCase:
    def __init__(self, repo: DetectionRepository) -> None:
        self._repo = repo

    async def create(self, payload: DetectionCreate) -> DetectionResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        created = await self._repo.create(doc)
        return DetectionResponse.model_validate(created)

    async def analyze_frame(
        self,
        client: InferenceClient,
        payload: bytes,
        session_id: int,
        frame_index: int,
        camera_id: str,
    ) -> DetectionResponse:
        result = await client.analyze(
            payload=payload,
            session_id=session_id,
            frame_index=frame_index,
        )
        now = datetime.now(timezone.utc)
        doc = {
            "session_id": session_id,
            "frame_index": frame_index,
            "timestamp": now.isoformat(),
            "camera_id": camera_id,
            "class_name": result.alert_type,
            "confidence": result.score,
            "bbox": result.bbox,
            "keypoints": result.keypoints,
            "created_at": now,
        }
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
