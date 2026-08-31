from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.database import close_mongodb_connection, connect_to_mongodb
from app.server import servicer as servicer_mod
from app.server.grpc_gen import alert_pb2
from app.server.servicer import AlertServicer
from app.shared.config import settings

pytestmark = pytest.mark.integration

COLL = settings.DELIVERY_INTENT_COLLECTION


def _alert(alert_id: str = "a-1") -> alert_pb2.Alert:
    request = alert_pb2.Alert(
        alert_id=alert_id,
        session_id=123,
        camera_id="cam-1",
        severity=alert_pb2.Alert.DESCRIPTOR.fields_by_name["severity"]
        .enum_type.values_by_name["SEVERITY_CRITICAL"]
        .number,
        alert_type=alert_pb2.Alert.DESCRIPTOR.fields_by_name["alert_type"]
        .enum_type.values_by_name["ALERT_TYPE_CONCEALMENT"]
        .number,
    )
    request.occurred_at.FromDatetime(datetime(2026, 6, 18, tzinfo=UTC))
    return request


@pytest.fixture
async def wired(
    test_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[MagicMock]:
    send_task = MagicMock()
    monkeypatch.setattr(servicer_mod.celery_app, "send_task", send_task)
    await connect_to_mongodb()
    try:
        yield send_task
    finally:
        await close_mongodb_connection()


def _context() -> MagicMock:
    ctx = MagicMock()
    ctx.set_code = MagicMock()
    ctx.set_details = MagicMock()
    return ctx


async def test_valid_alert_accepts_and_persists(
    wired: MagicMock, test_db: AsyncIOMotorDatabase
) -> None:
    reply = await AlertServicer().SendAlert(_alert(), _context())
    assert reply.status == alert_pb2.STATUS_ACCEPTED
    assert await test_db[COLL].count_documents({"source": "alert"}) == 1
    wired.assert_called_once()


async def test_invalid_alert_returns_failed(
    wired: MagicMock, test_db: AsyncIOMotorDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_: object) -> None:
        raise ValidationError.from_exception_data("AlertMessage", [])

    monkeypatch.setattr(servicer_mod.AlertMessage, "model_validate", _boom)
    reply = await AlertServicer().SendAlert(_alert(), _context())
    assert reply.status == alert_pb2.STATUS_FAILED
    assert await test_db[COLL].count_documents({}) == 0
    wired.assert_not_called()


async def test_enqueue_failure_still_accepts(
    wired: MagicMock, test_db: AsyncIOMotorDatabase
) -> None:
    wired.side_effect = RuntimeError("broker down")
    reply = await AlertServicer().SendAlert(_alert(), _context())
    assert reply.status == alert_pb2.STATUS_ACCEPTED
    assert await test_db[COLL].count_documents({"source": "alert"}) == 1


async def test_duplicate_alert_is_idempotent(
    wired: MagicMock, test_db: AsyncIOMotorDatabase
) -> None:
    first = await AlertServicer().SendAlert(_alert(), _context())
    second = await AlertServicer().SendAlert(_alert(), _context())
    assert first.status == alert_pb2.STATUS_ACCEPTED
    assert second.status == alert_pb2.STATUS_ACCEPTED
    assert await test_db[COLL].count_documents({"source": "alert"}) == 1
