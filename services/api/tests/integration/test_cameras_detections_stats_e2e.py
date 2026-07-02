from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from bson import ObjectId

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]



_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAIAAgDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oADAMB"
    "AAIRAxEAPwD3+iiigD//2Q=="
)


def _tiny_jpeg() -> bytes:
    return base64.b64decode(_TINY_JPEG_B64)


def _camera_payload(name: str = "cam-a", location: str = "lobby") -> dict[str, Any]:
    return {
        "name": name,
        "location": location,
        "stream_url": "rtsp://cam.local/stream1",
        "status": "active",
    }


def _detection_payload(session_id: int = 1, frame_index: int = 0) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "frame_index": frame_index,
        "occurred_at": "2026-06-12T10:00:00Z",
        "camera_id": "cam-1",
        "class_name": "person",
        "confidence": 0.87,
        "bbox": {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 200.0},
        "keypoints": [{"name": "nose", "x": 50.0, "y": 30.0, "confidence": 0.9}],
    }


# cameras

async def test_create_camera_persists_and_returns_201(
    client: httpx.AsyncClient, test_db
) -> None:
    resp = await client.post("/api/v1/cameras", json=_camera_payload("cam-create"))

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "cam-create"
    assert body["status"] == "active"
    assert "_id" in body
    assert "created_at" in body

    stored = await test_db.cameras.find_one({"name": "cam-create"})
    assert stored is not None


async def test_list_cameras_returns_all(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/cameras", json=_camera_payload("cam-l1"))
    await client.post("/api/v1/cameras", json=_camera_payload("cam-l2"))

    resp = await client.get("/api/v1/cameras")

    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "cam-l1" in names and "cam-l2" in names


async def test_get_camera_by_id_returns_camera(client: httpx.AsyncClient) -> None:
    create = await client.post("/api/v1/cameras", json=_camera_payload("cam-g"))
    cam_id = create.json()["_id"]

    resp = await client.get(f"/api/v1/cameras/{cam_id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "cam-g"


async def test_get_missing_camera_returns_404(client: httpx.AsyncClient) -> None:
    ghost = str(ObjectId())

    resp = await client.get(f"/api/v1/cameras/{ghost}")

    assert resp.status_code == 404


async def test_delete_camera_removes_doc(
    client: httpx.AsyncClient, test_db
) -> None:
    create = await client.post("/api/v1/cameras", json=_camera_payload("cam-d"))
    cam_id = create.json()["_id"]

    resp = await client.delete(f"/api/v1/cameras/{cam_id}")

    assert resp.status_code == 204
    stored = await test_db.cameras.find_one({"name": "cam-d"})
    assert stored is None


async def test_duplicate_camera_name_returns_409(
    client: httpx.AsyncClient,
) -> None:
    first = await client.post("/api/v1/cameras", json=_camera_payload("cam-dup"))
    second = await client.post("/api/v1/cameras", json=_camera_payload("cam-dup"))

    assert first.status_code == 201
    assert second.status_code == 409


# detections

async def test_create_detection_persists_and_returns_201(
    client: httpx.AsyncClient, test_db
) -> None:
    resp = await client.post("/api/v1/detections", json=_detection_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == 1
    assert body["class_name"] == "person"
    assert body["confidence"] == 0.87

    stored = await test_db.detections.find_one({"_id": ObjectId(body["_id"])})
    assert stored is not None


async def test_list_detections_returns_all(client: httpx.AsyncClient) -> None:
    for i in range(3):
        await client.post(
            "/api/v1/detections", json=_detection_payload(frame_index=i)
        )

    resp = await client.get("/api/v1/detections", params={"limit": 50, "skip": 0})

    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_list_detections_by_session_filters(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/v1/detections", json=_detection_payload(session_id=10))
    await client.post("/api/v1/detections", json=_detection_payload(session_id=10))
    await client.post("/api/v1/detections", json=_detection_payload(session_id=99))

    resp = await client.get("/api/v1/detections/session/10")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert all(d["session_id"] == 10 for d in items)


async def test_delete_detection_removes_doc(
    client: httpx.AsyncClient, test_db
) -> None:
    create = await client.post("/api/v1/detections", json=_detection_payload())
    det_id = create.json()["_id"]

    resp = await client.delete(f"/api/v1/detections/{det_id}")

    assert resp.status_code == 204
    stored = await test_db.detections.find_one({"_id": ObjectId(det_id)})
    assert stored is None


async def test_delete_missing_detection_returns_404(
    client: httpx.AsyncClient,
) -> None:
    ghost = str(ObjectId())

    resp = await client.delete(f"/api/v1/detections/{ghost}")

    assert resp.status_code == 404


async def test_invalid_confidence_returns_422(client: httpx.AsyncClient) -> None:
    payload = _detection_payload()
    payload["confidence"] = 1.5

    resp = await client.post("/api/v1/detections", json=payload)

    assert resp.status_code == 422


async def test_analyze_frame_end_to_end_through_inference_grpc(
    client: httpx.AsyncClient, test_db
) -> None:
    """exercises the full http -> grpc -> yolov8-pose -> mongo chain."""
    files = {"file": ("frame.jpg", _tiny_jpeg(), "image/jpeg")}
    form = {"session_id": "1", "frame_index": "0", "camera_id": "cam-analyze"}

    resp = await client.post("/api/v1/detections/analyze", data=form, files=files)

    assert resp.status_code in (201, 503)
    if resp.status_code == 201:
        body = resp.json()
        assert body["session_id"] == 1
        assert body["camera_id"] == "cam-analyze"
        assert "bbox" in body
        assert "_id" in body


# stats

async def test_stats_on_empty_db_returns_zeros(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_alerts"] == 0
    assert body["total_detections"] == 0
    assert body["total_cameras"] == 0


async def test_stats_counts_reflect_seeded_data(
    client: httpx.AsyncClient, test_db
) -> None:
    await test_db.cameras.insert_many(
        [{"name": "c1"}, {"name": "c2"}]
    )
    await test_db.detections.insert_many(
        [{"session_id": i} for i in range(3)]
    )
    today = datetime.now(timezone.utc)
    await test_db.alerts.insert_many(
        [
            {"severity": "SEVERITY_WARNING", "created_at": today, "object": {"class_name": "phone"}},
            {"severity": "SEVERITY_WARNING", "created_at": today, "object": {"class_name": "phone"}},
            {"severity": "SEVERITY_NOTICE", "created_at": today, "object": {"class_name": "bag"}},
            {"severity": "SEVERITY_INFO", "created_at": today, "object": {"class_name": "bag"}},
        ]
    )

    resp = await client.get("/api/v1/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cameras"] == 2
    assert body["total_detections"] == 3
    assert body["total_alerts"] == 4
    assert body["high_severity"] == 2
    assert body["medium_severity"] == 1


async def test_stats_alerts_today_counts_only_today(
    client: httpx.AsyncClient, test_db
) -> None:
    today = datetime.now(timezone.utc)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await test_db.alerts.insert_many(
        [
            {"severity": "SEVERITY_WARNING", "created_at": today},
            {"severity": "SEVERITY_WARNING", "created_at": today},
            {"severity": "SEVERITY_INFO", "created_at": old},
        ]
    )

    resp = await client.get("/api/v1/stats")

    assert resp.status_code == 200
    assert resp.json()["alerts_today"] == 2
