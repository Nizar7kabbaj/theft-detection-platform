from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.alert import AlertCreate, AlertPage, AlertResponse, AlertType, Severity

OCCURRED_AT = datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 6, 12, 10, 0, 1, tzinfo=UTC)

VALID_PAYLOAD = {
    "alert_id": "a1",
    "session_id": 1,
    "frame_index": 42,
    "occurred_at": OCCURRED_AT,
    "severity": "SEVERITY_WARNING",
}

VALID_RESPONSE_DOC = {
    "_id": "65f1a2b3c4d5e6f7a8b9c0d1",
    "alert_id": "a1",
    "session_id": 1,
    "occurred_at": OCCURRED_AT,
    "created_at": CREATED_AT,
    "camera_id": "cam-1",
    "severity": "SEVERITY_WARNING",
    "object_name": "phone",
}


class TestAlertCreate:
    def test_accepts_minimal_payload(self):
        alert = AlertCreate(**VALID_PAYLOAD)
        assert alert.alert_id == "a1"
        assert alert.session_id == 1
        assert alert.frame_index == 42
        assert alert.severity == Severity.SEVERITY_WARNING

    def test_defaults_applied_when_optional_fields_missing(self):
        alert = AlertCreate(**VALID_PAYLOAD)
        assert alert.camera_id == "default"
        assert alert.alert_type == AlertType.ALERT_TYPE_OBJECT_PROXIMITY
        assert alert.person is None
        assert alert.object is None
        assert alert.snapshot_path is None

    def test_session_id_must_be_int(self):
        payload = {**VALID_PAYLOAD, "session_id": "not-an-int"}
        with pytest.raises(ValidationError):
            AlertCreate(**payload)

    def test_frame_index_must_be_int(self):
        payload = {**VALID_PAYLOAD, "frame_index": "forty-two"}
        with pytest.raises(ValidationError):
            AlertCreate(**payload)

    def test_missing_required_field_rejected(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "severity"}
        with pytest.raises(ValidationError) as exc:
            AlertCreate(**payload)
        assert "severity" in str(exc.value)

    def test_optional_fields_accepted_when_provided(self):
        payload = {
            **VALID_PAYLOAD,
            "person": {
                "track_id": 1,
                "bbox": {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 200.0},
            },
            "object": {"class_name": "phone"},
            "snapshot_path": "snaps/a1.jpg",
            "alert_type": "ALERT_TYPE_BENDING",
        }
        alert = AlertCreate(**payload)
        assert alert.person.track_id == 1
        assert alert.person.bbox.x2 == 100.0
        assert alert.object.class_name == "phone"
        assert alert.snapshot_path == "snaps/a1.jpg"
        assert alert.alert_type == AlertType.ALERT_TYPE_BENDING


class TestAlertResponse:
    def test_accepts_doc_with_mongo_id_alias(self):
        resp = AlertResponse.model_validate(VALID_RESPONSE_DOC)
        assert resp.id == "65f1a2b3c4d5e6f7a8b9c0d1"
        assert resp.object_name == "phone"
        assert resp.severity == Severity.SEVERITY_WARNING

    def test_accepts_id_field_name_directly(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "_id"}
        doc["id"] = "abc123"
        resp = AlertResponse.model_validate(doc)
        assert resp.id == "abc123"

    def test_non_string_id_gets_stringified(self):
        doc = {**VALID_RESPONSE_DOC, "_id": 12345}
        resp = AlertResponse.model_validate(doc)
        assert resp.id == "12345"

    def test_optional_fields_default_to_none(self):
        resp = AlertResponse.model_validate(VALID_RESPONSE_DOC)
        assert resp.confidence is None
        assert resp.snapshot_url is None
        assert resp.alert_type is None
        assert resp.acknowledged is False
        assert resp.acknowledged_at is None

    def test_optional_fields_accepted_when_provided(self):
        doc = {
            **VALID_RESPONSE_DOC,
            "confidence": 0.87,
            "snapshot_url": "snaps/a1.jpg",
            "alert_type": "ALERT_TYPE_BENDING",
            "acknowledged": True,
            "acknowledged_at": CREATED_AT,
        }
        resp = AlertResponse.model_validate(doc)
        assert resp.confidence == 0.87
        assert resp.snapshot_url == "snaps/a1.jpg"
        assert resp.alert_type == AlertType.ALERT_TYPE_BENDING
        assert resp.acknowledged is True
        assert resp.acknowledged_at == CREATED_AT

    def test_created_at_is_required(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "created_at"}
        with pytest.raises(ValidationError) as exc:
            AlertResponse.model_validate(doc)
        assert "created_at" in str(exc.value)

    def test_created_at_kept_distinct_from_occurred_at(self):
        resp = AlertResponse.model_validate(VALID_RESPONSE_DOC)
        assert resp.occurred_at == OCCURRED_AT
        assert resp.created_at == CREATED_AT

    def test_missing_required_field_rejected(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "object_name"}
        with pytest.raises(ValidationError) as exc:
            AlertResponse.model_validate(doc)
        assert "object_name" in str(exc.value)

    def test_missing_id_rejected(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "_id"}
        with pytest.raises(ValidationError):
            AlertResponse.model_validate(doc)


class TestAlertPage:
    def test_wraps_items_and_defaults_cursor_to_none(self):
        page = AlertPage.model_validate({"items": [VALID_RESPONSE_DOC]})
        assert len(page.items) == 1
        assert page.items[0].alert_id == "a1"
        assert page.next_cursor is None

    def test_carries_next_cursor_when_present(self):
        page = AlertPage.model_validate({"items": [], "next_cursor": "abc"})
        assert page.items == []
        assert page.next_cursor == "abc"
