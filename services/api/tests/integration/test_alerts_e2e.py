from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import pytest_asyncio
from bson import ObjectId
from redis.asyncio import Redis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


def _alert_payload(
    alert_id: str = "test-a-1", severity: str = "SEVERITY_WARNING"
) -> dict[str, Any]:
    return {
        "alert_id": alert_id,
        "session_id": 1,
        "frame_index": 42,
        "occurred_at": "2026-06-12T10:00:00Z",
        "camera_id": "cam-1",
        "person": {
            "track_id": 7,
            "keypoints": [{"x": 0.5, "y": 0.5, "confidence": 0.9}],
        },
        "object": {"class_name": "phone"},
        "severity": severity,
        "snapshot_path": "snaps/a-1.jpg",
        "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
    }


@pytest_asyncio.fixture(loop_scope="session")
async def pubsub_listener(redis_client: Redis):
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("alerts:*")
    await asyncio.sleep(0.05)
    yield pubsub
    await pubsub.punsubscribe()
    await pubsub.aclose()


async def _drain(pubsub, timeout: float = 1.0) -> list[dict[str, Any]]:
    received: list[dict[str, Any]] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg is None:
            continue
        if msg["type"] not in ("message", "pmessage"):
            continue
        received.append(msg)
    return received


async def test_create_alert_persists_and_returns_201(
    client: httpx.AsyncClient,
    test_db,
) -> None:
    resp = await client.post("/api/v1/alerts", json=_alert_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["alert_id"] == "test-a-1"
    assert body["severity"] == "SEVERITY_WARNING"
    assert body["object_name"] == "phone"
    assert body["confidence"] is None
    assert "_id" in body

    stored = await test_db.alerts.find_one({"alert_id": "test-a-1"})
    assert stored is not None
    assert stored["session_id"] == 1
    assert stored["acknowledged"] is False
    assert "created_at" in stored


async def test_create_alert_publishes_to_pubsub(
    client: httpx.AsyncClient,
    pubsub_listener,
) -> None:
    await client.post("/api/v1/alerts", json=_alert_payload("test-a-pub"))
    messages = await _drain(pubsub_listener, timeout=1.5)

    channels = [m["channel"] for m in messages]
    assert "alerts:created" in channels
    created = next(m for m in messages if m["channel"] == "alerts:created")
    data = json.loads(created["data"])
    assert data["alert_id"] == "test-a-pub"


async def test_list_alerts_filters_by_severity(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/v1/alerts", json=_alert_payload("test-a-h1", "SEVERITY_WARNING"))
    await client.post("/api/v1/alerts", json=_alert_payload("test-a-h2", "SEVERITY_WARNING"))
    await client.post("/api/v1/alerts", json=_alert_payload("test-a-l1", "SEVERITY_NOTICE"))

    warning = await client.get("/api/v1/alerts", params={"severity": "SEVERITY_WARNING"})
    notice = await client.get("/api/v1/alerts", params={"severity": "SEVERITY_NOTICE"})

    assert warning.status_code == 200
    assert notice.status_code == 200
    assert len(warning.json()) == 2
    assert len(notice.json()) == 1
    assert all(item["severity"] == "SEVERITY_WARNING" for item in warning.json())


async def test_list_alerts_uses_redis_cache(
    client: httpx.AsyncClient,
    redis_client: Redis,
) -> None:
    await client.post("/api/v1/alerts", json=_alert_payload("test-a-cache"))
    await client.get("/api/v1/alerts", params={"limit": 50, "skip": 0})

    keys = [k async for k in redis_client.scan_iter("cache:alerts:list:*")]
    assert len(keys) >= 1


async def test_acknowledge_marks_doc_and_publishes(
    client: httpx.AsyncClient,
    test_db,
    pubsub_listener,
) -> None:
    create = await client.post("/api/v1/alerts", json=_alert_payload("test-a-ack"))
    mongo_id = create.json()["_id"]
    await _drain(pubsub_listener, timeout=0.3)

    resp = await client.patch(f"/api/v1/alerts/{mongo_id}/acknowledge")

    assert resp.status_code == 200
    assert resp.json()["alert_id"] == "test-a-ack"
    stored = await test_db.alerts.find_one({"alert_id": "test-a-ack"})
    assert stored["acknowledged"] is True
    assert "acknowledged_at" in stored

    messages = await _drain(pubsub_listener, timeout=1.0)
    channels = [m["channel"] for m in messages]
    assert "alerts:acknowledged" in channels


async def test_acknowledge_missing_alert_returns_404(
    client: httpx.AsyncClient,
) -> None:
    ghost_id = str(ObjectId())

    resp = await client.patch(f"/api/v1/alerts/{ghost_id}/acknowledge")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_acknowledge_malformed_id_returns_422(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.patch("/api/v1/alerts/not-a-real-oid/acknowledge")

    assert resp.status_code == 422


async def test_delete_alert_removes_doc_and_publishes(
    client: httpx.AsyncClient,
    test_db,
    pubsub_listener,
) -> None:
    create = await client.post("/api/v1/alerts", json=_alert_payload("test-a-del"))
    mongo_id = create.json()["_id"]
    await _drain(pubsub_listener, timeout=0.3)

    resp = await client.delete(f"/api/v1/alerts/{mongo_id}")

    assert resp.status_code == 204
    stored = await test_db.alerts.find_one({"alert_id": "test-a-del"})
    assert stored is None

    messages = await _drain(pubsub_listener, timeout=1.0)
    channels = [m["channel"] for m in messages]
    assert "alerts:deleted" in channels


async def test_delete_missing_alert_returns_404(
    client: httpx.AsyncClient,
) -> None:
    ghost_id = str(ObjectId())

    resp = await client.delete(f"/api/v1/alerts/{ghost_id}")

    assert resp.status_code == 404


async def test_idempotency_key_replays_first_response(
    client: httpx.AsyncClient,
    test_db,
) -> None:
    payload = _alert_payload("test-a-idem")
    headers = {"Idempotency-Key": "key-abc-123"}

    first = await client.post("/api/v1/alerts", json=payload, headers=headers)
    second = await client.post("/api/v1/alerts", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["alert_id"] == second.json()["alert_id"]

    count = await test_db.alerts.count_documents({"alert_id": "test-a-idem"})
    assert count == 1


async def test_idempotency_key_reuse_with_different_payload_conflicts(
    client: httpx.AsyncClient,
) -> None:
    headers = {"Idempotency-Key": "key-conflict"}

    first = await client.post(
        "/api/v1/alerts", json=_alert_payload("test-a-c1"), headers=headers
    )
    second = await client.post(
        "/api/v1/alerts", json=_alert_payload("test-a-c2"), headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 409
