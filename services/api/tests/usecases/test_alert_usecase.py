from datetime import UTC, datetime

import pytest

from app.core.errors import AlertUnavailableError, NotFoundError, ValidationError
from app.schemas.alert import AlertCreate, AlertPage, AlertResponse, AlertSort, AlertType
from app.usecases.alert_usecase import _to_response, decode_cursor, encode_cursor

OCCURRED_AT = datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 6, 12, 10, 0, 1, tzinfo=UTC)

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
        new=mocker.AsyncMock(return_value={"items": [], "next_cursor": None}),
    )
    mocker.patch(
        "app.usecases.alert_usecase.invalidate_prefix",
        new=mocker.AsyncMock(return_value=None),
    )


class TestCursorCodec:
    def test_round_trip_preserves_instant_and_id(self):
        token = encode_cursor(AlertSort.CREATED_AT.value, CREATED_AT, "oid-1")
        moment, id_ = decode_cursor(token, AlertSort.CREATED_AT.value)
        assert moment == CREATED_AT
        assert id_ == "oid-1"

    def test_token_carries_no_padding(self):
        assert "=" not in encode_cursor(AlertSort.CREATED_AT.value, CREATED_AT, "oid-1")

    def test_naive_timestamp_treated_as_utc(self):
        token = encode_cursor(AlertSort.CREATED_AT.value, CREATED_AT, "oid-1")
        moment, _ = decode_cursor(token, AlertSort.CREATED_AT.value)
        assert moment.tzinfo is not None

    def test_garbage_token_rejected(self):
        with pytest.raises(ValidationError, match="malformed cursor"):
            decode_cursor("not-base64-at-all!!", AlertSort.CREATED_AT.value)

    def test_token_without_separator_rejected(self):
        import base64

        raw = base64.urlsafe_b64encode(b"no-separator-here").decode().rstrip("=")
        with pytest.raises(ValidationError, match="malformed cursor"):
            decode_cursor(raw, AlertSort.CREATED_AT.value)

    def test_token_with_unparseable_timestamp_rejected(self):
        import base64

        raw = base64.urlsafe_b64encode(b"created_at|yesterday|oid-1").decode().rstrip("=")
        with pytest.raises(ValidationError, match="malformed cursor"):
            decode_cursor(raw, AlertSort.CREATED_AT.value)

    def test_cursor_from_other_sort_order_rejected(self):
        token = encode_cursor(AlertSort.CREATED_AT.value, CREATED_AT, "oid-1")
        with pytest.raises(ValidationError, match="does not match"):
            decode_cursor(token, AlertSort.DECIDED_AT.value)


class TestToResponse:
    def test_object_present_uses_class_name_and_confidence(self):
        doc = {
            "_id": "oid-1",
            "alert_id": "a1",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "created_at": CREATED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object": {"class_name": "phone", "confidence": 0.92},
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        }
        resp = _to_response(doc)
        assert resp.object_name == "phone"
        assert resp.confidence == 0.92
        assert resp.alert_type == AlertType.ALERT_TYPE_OBJECT_PROXIMITY

        doc = {
            "_id": "oid-2",
            "alert_id": "a2",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "created_at": CREATED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_NOTICE",
            "object": None,
        }
        resp = _to_response(doc)
        assert resp.confidence is None

    def test_object_absent_falls_back_to_alert_type_string(self):
        doc = {
            "_id": "oid-3",
            "alert_id": "a3",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "created_at": CREATED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_INFO",
            "object": None,
            "alert_type": "ALERT_TYPE_LOITERING",
        }
        resp = _to_response(doc)
        assert resp.object_name == "loitering"

    def test_flat_document_keeps_its_stored_fields(self):
        doc = {
            "_id": "oid-4",
            "alert_id": "a4",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "created_at": CREATED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object_name": "backpack",
            "confidence": 0.71,
            "alert_type": "ALERT_TYPE_LOITERING",
        }
        resp = _to_response(doc)
        assert resp.object_name == "backpack"
        assert resp.confidence == 0.71

    def test_missing_created_at_falls_back_to_occurred_at(self):
        doc = {
            "_id": "oid-5",
            "alert_id": "a5",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_INFO",
            "object_name": "phone",
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        }
        resp = _to_response(doc)
        assert resp.created_at == OCCURRED_AT

    def test_acknowledged_state_carried_through(self):
        doc = {
            "_id": "oid-6",
            "alert_id": "a6",
            "session_id": 1,
            "occurred_at": OCCURRED_AT,
            "created_at": CREATED_AT,
            "camera_id": "cam-1",
            "severity": "SEVERITY_INFO",
            "object_name": "phone",
            "acknowledged": True,
            "acknowledged_at": CREATED_AT,
        }
        resp = _to_response(doc)
        assert resp.acknowledged is True
        assert resp.acknowledged_at == CREATED_AT


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
        mock_alert_client.send.side_effect = AlertUnavailableError("downstream down")
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
    async def test_returns_page_parsed_from_cache(self, alert_usecase, mocker):
        cached_item = {
            "_id": "oid-1",
            "alert_id": "a1",
            "session_id": 1,
            "occurred_at": OCCURRED_AT.isoformat(),
            "created_at": CREATED_AT.isoformat(),
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object_name": "phone",
            "confidence": 0.92,
            "snapshot_url": "snaps/a1.jpg",
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
            "acknowledged": False,
            "acknowledged_at": None,
        }
        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(return_value={"items": [cached_item], "next_cursor": "tok"}),
        )
        page = await alert_usecase.list()
        assert isinstance(page, AlertPage)
        assert len(page.items) == 1
        assert page.items[0].alert_id == "a1"
        assert page.next_cursor == "tok"

    async def test_empty_cache_returns_empty_page(self, alert_usecase):
        page = await alert_usecase.list()
        assert page.items == []
        assert page.next_cursor is None

    async def test_loader_pulls_from_repo_on_cache_miss(
        self, alert_usecase, fake_alert_repo, mocker, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {
            **sample_alert_doc,
            "created_at": CREATED_AT,
        }

        async def call_loader(_redis, _key, _ttl, loader):
            return await loader()

        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(side_effect=call_loader),
        )
        page = await alert_usecase.list()
        assert len(page.items) == 1
        assert page.items[0].alert_id == "a1"
        assert page.next_cursor is None

    async def test_short_page_reports_no_next_cursor(self, alert_usecase, fake_alert_repo, mocker):
        for index in range(3):
            fake_alert_repo.store[f"oid-{index}"] = {
                "_id": f"oid-{index}",
                "alert_id": f"a{index}",
                "session_id": 1,
                "occurred_at": OCCURRED_AT,
                "created_at": CREATED_AT,
                "camera_id": "cam-1",
                "severity": "SEVERITY_INFO",
                "object_name": "phone",
                "acknowledged": False,
            }

        async def call_loader(_redis, _key, _ttl, loader):
            return await loader()

        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(side_effect=call_loader),
        )
        page = await alert_usecase.list(limit=10)
        assert len(page.items) == 3
        assert page.next_cursor is None

    async def test_full_page_hands_out_cursor_and_drops_probe_row(
        self, alert_usecase, fake_alert_repo, mocker
    ):
        for index in range(5):
            fake_alert_repo.store[f"oid-{index}"] = {
                "_id": f"oid-{index}",
                "alert_id": f"a{index}",
                "session_id": 1,
                "occurred_at": OCCURRED_AT,
                "created_at": CREATED_AT,
                "camera_id": "cam-1",
                "severity": "SEVERITY_INFO",
                "object_name": "phone",
                "acknowledged": False,
            }

        async def call_loader(_redis, _key, _ttl, loader):
            return await loader()

        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(side_effect=call_loader),
        )
        page = await alert_usecase.list(limit=2)
        assert len(page.items) == 2
        assert page.next_cursor is not None
        _moment, id_ = decode_cursor(page.next_cursor, AlertSort.CREATED_AT.value)
        assert id_ == page.items[-1].id

    async def test_second_page_does_not_repeat_first(self, alert_usecase, fake_alert_repo, mocker):
        for index in range(5):
            fake_alert_repo.store[f"oid-{index}"] = {
                "_id": f"oid-{index}",
                "alert_id": f"a{index}",
                "session_id": 1,
                "occurred_at": OCCURRED_AT,
                "created_at": CREATED_AT,
                "camera_id": "cam-1",
                "severity": "SEVERITY_INFO",
                "object_name": "phone",
                "acknowledged": False,
            }

        async def call_loader(_redis, _key, _ttl, loader):
            return await loader()

        mocker.patch(
            "app.usecases.alert_usecase.get_or_set",
            new=mocker.AsyncMock(side_effect=call_loader),
        )
        first = await alert_usecase.list(limit=2)
        second = await alert_usecase.list(limit=2, cursor=first.next_cursor)
        first_ids = {item.id for item in first.items}
        second_ids = {item.id for item in second.items}
        assert first_ids & second_ids == set()

    async def test_malformed_cursor_rejected_before_any_read(self, alert_usecase):
        with pytest.raises(ValidationError, match="malformed cursor"):
            await alert_usecase.list(cursor="garbage!!")


class TestAcknowledge:
    async def test_marks_alert_acknowledged(self, alert_usecase, fake_alert_repo, sample_alert_doc):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        resp = await alert_usecase.acknowledge(sample_alert_doc["_id"], "user-1")
        assert isinstance(resp, AlertResponse)
        assert fake_alert_repo.store[sample_alert_doc["_id"]]["acknowledged"] is True

    async def test_raises_not_found_for_missing_alert(self, alert_usecase):
        with pytest.raises(NotFoundError, match="not found"):
            await alert_usecase.acknowledge("missing-id", "user-1")

    async def test_publishes_acknowledged_event(
        self, alert_usecase, fake_alert_repo, mock_redis, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        await alert_usecase.acknowledge(sample_alert_doc["_id"], "user-1")
        channel, _ = mock_redis.publish.await_args.args
        assert channel == "alerts:acknowledged"

    async def test_repeat_acknowledge_does_not_republish(
        self, alert_usecase, fake_alert_repo, mock_redis, sample_alert_doc
    ):
        fake_alert_repo.store[sample_alert_doc["_id"]] = {**sample_alert_doc}
        await alert_usecase.acknowledge(sample_alert_doc["_id"], "user-1")
        assert mock_redis.publish.await_count == 1
        await alert_usecase.acknowledge(sample_alert_doc["_id"], "user-1")
        assert mock_redis.publish.await_count == 1
