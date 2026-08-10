from datetime import datetime
from typing import Any

import pytest

from app.core.config import settings
from app.grpc_gen import inference_pb2 as pb
from app.schemas.alert import AlertType, Severity
from app.schemas.detection import DetectionResponse
from app.services.inference_service import InferenceResult
from app.usecases.detection_usecase import DetectionUseCase, _severity_from_score


class FakeDetectionRepo:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        oid = f"oid-{self._next_id}"
        self._next_id += 1
        doc = {**data, "_id": oid}
        self.store[oid] = doc
        return doc

    async def list_recent(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        docs = list(self.store.values())
        return docs[skip : skip + limit]

    async def list_by_session(self, session_id: int) -> list[dict[str, Any]]:
        return [d for d in self.store.values() if d.get("session_id") == session_id]

    async def delete(self, id_: str) -> bool:
        return self.store.pop(id_, None) is not None


@pytest.fixture
def fake_detection_repo() -> FakeDetectionRepo:
    return FakeDetectionRepo()


@pytest.fixture
def mock_alert_usecase(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def detection_usecase(fake_detection_repo, mock_alert_usecase) -> DetectionUseCase:
    return DetectionUseCase(repo=fake_detection_repo, alert_usecase=mock_alert_usecase)


@pytest.fixture
def mock_inference_client(mocker):
    return mocker.AsyncMock()


def _inference_result(
    score: float,
    inference_state: int = pb.InferenceState.INFERENCE_STATE_ANOMALY,
) -> InferenceResult:
    return InferenceResult(
        bbox={"x1": 10.0, "y1": 20.0, "x2": 110.0, "y2": 220.0},
        keypoints=[{"x": 50.0, "y": 100.0, "confidence": 0.9}],
        score=score,
        inference_state=inference_state,
        track_id=7,
        detection_present=True,
    )


class TestSeverityFromScore:
    def test_score_at_warning_boundary_returns_warning(self):
        assert _severity_from_score(0.9) == Severity.SEVERITY_WARNING

    def test_score_above_warning_boundary_returns_warning(self):
        assert _severity_from_score(0.95) == Severity.SEVERITY_WARNING

    def test_score_just_below_warning_returns_notice(self):
        assert _severity_from_score(0.89) == Severity.SEVERITY_NOTICE

    def test_low_score_returns_notice(self):
        assert _severity_from_score(0.0) == Severity.SEVERITY_NOTICE


class TestAnalyzeFrameAlertTrigger:
    async def test_high_score_raises_warning_alert_with_mapped_type(
        self, detection_usecase, mock_inference_client, mock_alert_usecase
    ):
        mock_inference_client.analyze.return_value = _inference_result(score=0.95)

        await detection_usecase.analyze_frame(
            client=mock_inference_client,
            payload=b"frame-bytes",
            session_id=1,
            frame_index=10,
            camera_id="cam-1",
        )

        mock_alert_usecase.create.assert_awaited_once()
        alert_payload = mock_alert_usecase.create.await_args.args[0]
        assert alert_payload.severity == Severity.SEVERITY_WARNING
        assert alert_payload.alert_type == AlertType.ALERT_TYPE_OBJECT_PROXIMITY
        assert alert_payload.session_id == 1
        assert alert_payload.frame_index == 10
        assert alert_payload.camera_id == "cam-1"

    async def test_below_threshold_score_does_not_raise_alert(
        self, detection_usecase, mock_inference_client, mock_alert_usecase
    ):
        mock_inference_client.analyze.return_value = _inference_result(
            score=settings.ALERT_THRESHOLD - 0.01
        )

        await detection_usecase.analyze_frame(
            client=mock_inference_client,
            payload=b"frame-bytes",
            session_id=3,
            frame_index=30,
            camera_id="cam-3",
        )

        mock_alert_usecase.create.assert_not_awaited()

    async def test_alert_creation_failure_does_not_break_detection(
        self, detection_usecase, mock_inference_client, mock_alert_usecase, fake_detection_repo
    ):
        mock_inference_client.analyze.return_value = _inference_result(score=0.95)
        mock_alert_usecase.create.side_effect = Exception("alert service down")

        response = await detection_usecase.analyze_frame(
            client=mock_inference_client,
            payload=b"frame-bytes",
            session_id=4,
            frame_index=40,
            camera_id="cam-4",
        )

        assert isinstance(response, DetectionResponse)
        assert len(fake_detection_repo.store) == 1

    async def test_detection_persisted_regardless_of_alert_outcome(
        self, detection_usecase, mock_inference_client, fake_detection_repo
    ):
        mock_inference_client.analyze.return_value = _inference_result(score=0.95)

        await detection_usecase.analyze_frame(
            client=mock_inference_client,
            payload=b"frame-bytes",
            session_id=5,
            frame_index=50,
            camera_id="cam-5",
        )

        assert len(fake_detection_repo.store) == 1
        stored = next(iter(fake_detection_repo.store.values()))
        assert stored["session_id"] == 5
        assert stored["frame_index"] == 50
        assert isinstance(stored["created_at"], datetime)
