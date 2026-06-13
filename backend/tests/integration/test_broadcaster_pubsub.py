from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import websockets
from redis.asyncio import Redis

from app.services.broadcast_service import BroadcastService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _recv_with_timeout(
    ws: websockets.ClientConnection, timeout: float = 2.0
) -> dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


async def _recv_until_event(
    ws: websockets.ClientConnection,
    event_name: str,
    timeout: float = 2.0,
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"never saw event={event_name}")
        envelope = await _recv_with_timeout(ws, timeout=remaining)
        if envelope.get("event") == event_name:
            return envelope


async def test_ws_connects_and_receives_alert_event(
    ws_server: tuple[str, BroadcastService],
    redis_client: Redis,
) -> None:
    base_url, _ = ws_server
    async with websockets.connect(f"{base_url}/ws/alerts") as ws:
        await asyncio.sleep(0.1)

        payload = {"alert_id": "ws-1", "severity": "HIGH"}
        await redis_client.publish("alerts:created", json.dumps(payload))

        envelope = await _recv_until_event(ws, "created")
        assert envelope["event"] == "created"
        assert envelope["data"] == payload


async def test_ws_receives_multiple_events(
    ws_server: tuple[str, BroadcastService],
    redis_client: Redis,
) -> None:
    base_url, _ = ws_server
    async with websockets.connect(f"{base_url}/ws/alerts") as ws:
        await asyncio.sleep(0.1)

        await redis_client.publish(
            "alerts:created", json.dumps({"alert_id": "ws-m1"})
        )
        await redis_client.publish(
            "alerts:acknowledged", json.dumps({"alert_id": "ws-m1"})
        )
        await redis_client.publish(
            "alerts:deleted", json.dumps({"alert_id": "ws-m1"})
        )

        created = await _recv_until_event(ws, "created")
        ack = await _recv_until_event(ws, "acknowledged")
        deleted = await _recv_until_event(ws, "deleted")

        assert created["data"]["alert_id"] == "ws-m1"
        assert ack["data"]["alert_id"] == "ws-m1"
        assert deleted["data"]["alert_id"] == "ws-m1"


async def test_ws_topic_isolation(
    ws_server: tuple[str, BroadcastService],
    redis_client: Redis,
) -> None:
    base_url, _ = ws_server
    async with websockets.connect(f"{base_url}/ws/alerts") as ws:
        await asyncio.sleep(0.1)

        await redis_client.publish(
            "cameras:created", json.dumps({"camera_id": "iso-1"})
        )

        with pytest.raises(asyncio.TimeoutError):
            await _recv_until_event(ws, "created", timeout=0.5)


async def test_ws_unknown_topic_closes(
    ws_server: tuple[str, BroadcastService],
) -> None:
    base_url, _ = ws_server
    # routes only exist for /ws/alerts and /ws/cameras; anything else 404s
    # at the http handshake layer
    with pytest.raises(
        (
            websockets.exceptions.InvalidStatus,
            websockets.exceptions.ConnectionClosed,
        )
    ):
        async with websockets.connect(f"{base_url}/ws/unknown"):
            pass


async def test_ws_drops_non_json_pubsub_message(
    ws_server: tuple[str, BroadcastService],
    redis_client: Redis,
) -> None:
    base_url, _ = ws_server
    async with websockets.connect(f"{base_url}/ws/alerts") as ws:
        await asyncio.sleep(0.1)

        await redis_client.publish("alerts:created", "not-valid-json")
        await redis_client.publish(
            "alerts:created", json.dumps({"alert_id": "ws-survives"})
        )

        envelope = await _recv_until_event(ws, "created")
        assert envelope["data"]["alert_id"] == "ws-survives"
