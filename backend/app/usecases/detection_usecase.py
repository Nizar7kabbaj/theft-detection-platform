from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import settings
from app.core.errors import NotFoundError
from app.repositories.detection_repository import DetectionRepository
from app.schemas.alert import AlertCreate
from app.schemas.detection import DetectionCreate, DetectionResponse
from app.services.inference_service import InferenceClient, InferenceResult
from app.usecases.alert_usecase import AlertUseCase

logger = logging.getLogger(__name__)


def _severity_from_score(score: float) -> str:
    if score >= 0.9:
        return "HIGH"
    return "MEDIUM"


class DetectionUseCase:
    def __init__(self, repo: DetectionRepository, alert_usecase: AlertUseCase) -> None:
        self._repo = repo
        self._alert_usecase = alert_usecase

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
        timestamp = now.isoformat()

        doc = {
            "session_id": session_id,
            "frame_index": frame_index,
            "timestamp": timestamp,
            "camera_id": camera_id,
            "class_name": result.alert_type,
            "confidence": result.score,
            "bbox": result.bbox,
            "keypoints": result.keypoints,
            "created_at": now,
        }
        created = await self._repo.create(doc)
        response = DetectionResponse.model_validate(created)

        if result.score >= settings.ALERT_THRESHOLD:
            await self._maybe_raise_alert(
                result=result,
                session_id=session_id,
                frame_index=frame_index,
                camera_id=camera_id,
                timestamp=timestamp,
            )

        return response

    async def _maybe_raise_alert(
        self,
        result: InferenceResult,
        session_id: int,
        frame_index: int,
        camera_id: str,
        timestamp: str,
    ) -> None:
        try:
            payload = AlertCreate(
                alert_id=uuid4().hex,
                session_id=session_id,
                frame_index=frame_index,
                timestamp=timestamp,
                camera_id=camera_id,
                person={},
                severity=_severity_from_score(result.score),
                alert_type=result.alert_type,
                keypoints=result.keypoints,
            )
            await self._alert_usecase.create(payload)
        except Exception as exc:
            logger.warning(
                "alert creation failed for session=%s frame=%s: %s",
                session_id,
                frame_index,
                exc,
            )

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
