from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import settings
from app.core.errors import NotFoundError
from app.grpc_gen import inference_pb2 as pb
from app.repositories.detection_repository import DetectionRepository
from app.schemas.alert import AlertCreate, AlertType, Severity
from app.schemas.detection import DetectionCreate, DetectionResponse
from app.services.inference_service import InferenceClient, InferenceResult
from app.usecases.alert_usecase import AlertUseCase

logger = logging.getLogger(__name__)


_INFERENCE_TO_ALERT_TYPE: dict[int, AlertType] = {
    pb.InferenceState.INFERENCE_STATE_ANOMALY: AlertType.ALERT_TYPE_OBJECT_PROXIMITY,
}

_WARNING_SCORE_THRESHOLD = 0.9


def _severity_from_score(score: float) -> Severity:
    if score >= _WARNING_SCORE_THRESHOLD:
        return Severity.SEVERITY_WARNING
    return Severity.SEVERITY_NOTICE


def _alert_type_from_state(state: int) -> AlertType:
    return _INFERENCE_TO_ALERT_TYPE.get(state, AlertType.ALERT_TYPE_UNSPECIFIED)


class DetectionUseCase:
    def __init__(self, repo: DetectionRepository, alert_usecase: AlertUseCase) -> None:
        self._repo = repo
        self._alert_usecase = alert_usecase

    async def create(self, payload: DetectionCreate) -> DetectionResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(UTC)
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
        now = datetime.now(UTC)

        doc = {
            "session_id": session_id,
            "frame_index": frame_index,
            "occurred_at": now,
            "camera_id": camera_id,
            "class_name": pb.InferenceState.Name(result.inference_state),
            "confidence": result.score,
            "bbox": result.bbox,
            "keypoints": result.keypoints,
            "track_id": result.track_id,
            "detection_present": result.detection_present,
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
                occurred_at=now,
            )

        return response

    async def _maybe_raise_alert(
        self,
        result: InferenceResult,
        session_id: int,
        frame_index: int,
        camera_id: str,
        occurred_at: datetime,
    ) -> None:
        try:
            payload = AlertCreate(
                alert_id=uuid4().hex,
                session_id=session_id,
                frame_index=frame_index,
                occurred_at=occurred_at,
                camera_id=camera_id,
                person=None,
                severity=_severity_from_score(result.score),
                alert_type=_alert_type_from_state(result.inference_state),
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
