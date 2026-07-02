from datetime import datetime, timezone

import pytest

from app.core.errors import AlertUnavailable, NotFoundError
from app.schemas.alert import AlertCreate, AlertResponse, AlertType
from app.usecases.alert_usecase import _to_response


OCCURRED_AT = datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)


VALID_PAYLOAD = {
    "alert_id": "a1",
    "session_id": 1,
    "frame_index": 42,
    "occurred_at": OCCURRED_AT,
    "person": {
        "track_id": 1,
        "bbox": {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 200.0},
    },
    "severity": "SEVERITY_WARNING",
    "object": {"class_name": "phone"},
}


@pytest.fixture(autouse=True)
def patch_cache(mocker):
    mocker.patch(
        "app.usecases.alert_usecase.get_or_set",
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        "app.usecases.alert_usecase.invalidate_prefix",
        new=mocker.AsyncMock(return_value=None),
    )


class TestToResponse:
    def test_object_present_uses_class_name_and_confidence(self):
        doc = {
            "_id": "oid-1",
            "alert_id": "a1",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object": {"class_name": "phone", "confidence": 0.92},
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        }
        resp = _to_response(doc)
        assert resp.object_name == "phone"
        assert resp.confidence == 0.92
        assert resp.alert_type == AlertType.ALERT_TYPE_OBJECT_PROXIMITY

    def test_object_absent_with_bending_type_falls_back_to_readable_string(self):
        doc = {
            "_id": "oid-2",
            "alert_id": "a2",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_NOTICE",
            "object": None,
            "alert_type": "ALERT_TYPE_BENDING",
        }
        resp = _to_response(doc)
        assert resp.object_name == "bending"
        assert resp.confidence is None
        assert resp.alert_type == AlertType.ALERT_TYPE_BENDING

    def test_object_absent_falls_back_to_alert_type_string(self):
        doc = {
            "_id": "oid-3",
            "alert_id": "a3",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_INFO",
            "object": None,
            "alert_type": "ALERT_TYPE_LOITERING",
        }
        resp = _to_response(doc)
        assert resp.object_name == "loitering"


class TestCreate:
    async def test_persists_alert_and_returns_response(self, alert_usecase, fake_alert_repo):
        payload = AlertCreate(**VALID_PAYLOAD)
        resp = await alert_usecase.create(payload)
        assert isinstance(resp, AlertResponse)
        assert resp.alert_id == "a1"
        assert len(fake_alert_repo.store) == 1
        stored = next(iter(fake_alert_repo.store.values()))
        assert stored["acknowledged"] is False
        assert isinstance(stored["created_at"], datetime)

    async def test_calls_alert_client_send(self, alert_usecase, mock_alert_client):
        payload = AlertCreate(**VALID_PAYLOAD)
        await alert_usecase.create(payload)
        mock_alert_client.send.assert_awaited_once()

    async def test_swallows_alert_unavailable(self, alert_usecase, mock_alert_client):
        mock_alert_client.send.side_effect = AlertUnavailable("downstream down")
        payload = AlertCreate(**VALID_PAYLOAD)
        resp = await alert_usecase.create(payload)
        assert resp.alert_id == "a1"

    async def test_publishes_created_event(self, alert_usecase, mock_redis):
        payload = AlertCreate(**VALID_PAYLOAD)
        await alert_usecase.create(payload)
        mock_redis.publish.assert_awaited()
        channel, _ = mock_redis.publish.await_args.args
        assert channel == "alerts:created"

    async def test_publish_failure_does_not_raise(self, alert_usecase, mock_redis):
        mock_redis.publish.side_effect = Exception("redis down")
        payload = AlertCreate(**VALID_PAYLOAD)
        resp = await alert_usecase.create(payload)
        assert resp.alert_id == "a1"


class TestList:
    async def test_returns_parsed_responses_from_cache(self, alert_usecase, mocker):
        cached_item = {
            "_id": "oid-1",
            "alert_id": "a1",
            "session_id": 1,
            "occurred_at": OCCURRED_AT.isoformat(),
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object_name": "phone",
            "confidence": 0.92,
            "snapshot_url": "snaps/a1.jpg",
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        }
        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(return_value=[cached_item]),
        )
        results = await alert_usecase.list()
        assert len(results) == 1
        assert isinstance(results[0], AlertResponse)
        assert results[0].alert_id == "a1"

    async def test_empty_cache_returns_empty_list(self, alert_usecase):
        results = await alert_usecase.list()
        assert results == []

    async def test_loader_pulls_from_repo_on_cache_miss(
        self, alert_usecase, fake_alert_repo, mocker, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {
            **sample_alert_doc,
            "created_at": datetime.now(timezone.utc),
        }

        async def call_loader(_redis, _key, _ttl, loader):
            return await loader()

        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(side_effect=call_loader),
        )
        results = await alert_usecase.list()
        assert len(results) == 1
        assert results[0].alert_id == "a1"


class TestAcknowledge:
    async def test_marks_alert_acknowledged(
        self, alert_usecase, fake_alert_repo, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        resp = await alert_usecase.acknowledge(sample_alert_doc["_id"])
        assert isinstance(resp, AlertResponse)
        assert fake_alert_repo.store[sample_alert_doc["_id"]]["acknowledged"] is True

    async def test_raises_not_found_for_missing_alert(self, alert_usecase):
        with pytest.raises(NotFoundError, match="not found"):
            await alert_usecase.acknowledge("missing-id")

    async def test_publishes_acknowledged_event(
        self, alert_usecase, fake_alert_repo, mock_redis, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        await alert_usecase.acknowledge(sample_alert_doc["_id"])
        channel, _ = mock_redis.publish.await_args.args
        assert channel == "alerts:acknowledged"


class TestDelete:
    async def test_removes_alert(self, alert_usecase, fake_alert_repo, sample_alert_doc):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        await alert_usecase.delete(sample_alert_doc["_id"])
        assert sample_alert_doc["_id"] not in fake_alert_repo.store

    async def test_raises_not_found_for_missing_alert(self, alert_usecase):
        with pytest.raises(NotFoundError, match="not found"):
            await alert_usecase.delete("missing-id")

    async def test_publish_failure_does_not_raise(
        self, alert_usecase, fake_alert_repo, mock_redis, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        mock_redis.publish.side_effect = Exception("redis down")
        await alert_usecase.delete(sample_alert_doc["_id"])
        assert sample_alert_doc["_id"] not in fake_alert_repo.store
