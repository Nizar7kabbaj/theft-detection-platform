import pytest
from pydantic import ValidationError

from app.schemas.alert import AlertCreate, AlertResponse


VALID_PAYLOAD = {
    "alert_id": "a1",
    "session_id": 1,
    "frame_index": 42,
    "timestamp": "2026-06-12T10:00:00Z",
    "person": {"id": 1, "bbox": [0, 0, 100, 200]},
    "severity": "high",
}


VALID_RESPONSE_DOC = {
    "_id": "65f1a2b3c4d5e6f7a8b9c0d1",
    "alert_id": "a1",
    "session_id": 1,
    "timestamp": "2026-06-12T10:00:00Z",
    "camera_id": "cam-1",
    "severity": "high",
    "object_name": "phone",
}


class TestAlertCreate:
    def test_accepts_minimal_payload(self):
        alert = AlertCreate(**VALID_PAYLOAD)
        assert alert.alert_id == "a1"
        assert alert.session_id == 1
        assert alert.frame_index == 42

    def test_defaults_applied_when_optional_fields_missing(self):
        alert = AlertCreate(**VALID_PAYLOAD)
        assert alert.camera_id == "default"
        assert alert.alert_type == "object_proximity"
        assert alert.object is None
        assert alert.snapshot_path is None
        assert alert.keypoints is None
        assert alert.torso_angle is None

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
            "object": {"class_name": "phone", "confidence": 0.92},
            "snapshot_path": "snaps/a1.jpg",
            "alert_type": "bending",
            "torso_angle": 75.4,
            "keypoints": [{"x": 1.0, "y": 2.0, "confidence": 0.9}],
        }
        alert = AlertCreate(**payload)
        assert alert.object == {"class_name": "phone", "confidence": 0.92}
        assert alert.alert_type == "bending"
        assert alert.torso_angle == 75.4

    def test_person_field_is_required(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "person"}
        with pytest.raises(ValidationError) as exc:
            AlertCreate(**payload)
        assert "person" in str(exc.value)


class TestAlertResponse:
    def test_accepts_doc_with_mongo_id_alias(self):
        resp = AlertResponse.model_validate(VALID_RESPONSE_DOC)
        assert resp.id == "65f1a2b3c4d5e6f7a8b9c0d1"
        assert resp.object_name == "phone"

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

    def test_optional_fields_accepted_when_provided(self):
        doc = {
            **VALID_RESPONSE_DOC,
            "confidence": 0.87,
            "snapshot_url": "snaps/a1.jpg",
            "alert_type": "bending",
        }
        resp = AlertResponse.model_validate(doc)
        assert resp.confidence == 0.87
        assert resp.snapshot_url == "snaps/a1.jpg"
        assert resp.alert_type == "bending"

    def test_missing_required_field_rejected(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "object_name"}
        with pytest.raises(ValidationError) as exc:
            AlertResponse.model_validate(doc)
        assert "object_name" in str(exc.value)

    def test_missing_id_rejected(self):
        doc = {k: v for k, v in VALID_RESPONSE_DOC.items() if k != "_id"}
        with pytest.raises(ValidationError):
            AlertResponse.model_validate(doc)
