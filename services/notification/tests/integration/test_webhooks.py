from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import close_mongodb_connection, connect_to_mongodb
from app.server.api import webhooks
from app.server.http_app import create_app
from app.shared.config import settings

pytestmark = pytest.mark.integration

COLL = settings.DELIVERY_INTENT_COLLECTION
TOKEN = "test-token-value"


@pytest.fixture
def token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "webhook_token"
    path.write_text(TOKEN)
    monkeypatch.setattr(webhooks.settings, "ALERTMANAGER_WEBHOOK_TOKEN_FILE", path)
    webhooks._reset_token_cache()
    yield path
    webhooks._reset_token_cache()


@pytest.fixture
async def client(
    test_db: AsyncIOMotorDatabase, token_file: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(webhooks.celery_app, "send_task", MagicMock())
    await connect_to_mongodb()
    transport = ASGITransport(app=create_app())
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        await close_mongodb_connection()


async def _post(client: AsyncClient, payload: dict, token: str | None = TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return await client.post("/webhooks/alertmanager", json=payload, headers=headers)


async def test_valid_post_accepts_and_persists(
    client: AsyncClient, alertmanager_payload: dict, test_db: AsyncIOMotorDatabase
) -> None:
    response = await _post(client, alertmanager_payload)
    assert response.status_code == 202
    assert await test_db[COLL].count_documents({"source": "alertmanager"}) == 1
    webhooks.celery_app.send_task.assert_called_once()


async def test_missing_token_returns_401(
    client: AsyncClient, alertmanager_payload: dict, test_db: AsyncIOMotorDatabase
) -> None:
    response = await _post(client, alertmanager_payload, token=None)
    assert response.status_code == 401
    assert await test_db[COLL].count_documents({}) == 0
    webhooks.celery_app.send_task.assert_not_called()


async def test_wrong_token_returns_401(
    client: AsyncClient, alertmanager_payload: dict, test_db: AsyncIOMotorDatabase
) -> None:
    response = await _post(client, alertmanager_payload, token="wrong-token")
    assert response.status_code == 401
    assert await test_db[COLL].count_documents({}) == 0
    webhooks.celery_app.send_task.assert_not_called()


async def test_malformed_payload_returns_422(
    client: AsyncClient, alertmanager_payload: dict, test_db: AsyncIOMotorDatabase
) -> None:
    bad = {k: v for k, v in alertmanager_payload.items() if k != "status"}
    response = await _post(client, bad)
    assert response.status_code == 422
    assert await test_db[COLL].count_documents({}) == 0
    webhooks.celery_app.send_task.assert_not_called()


async def test_duplicate_post_is_idempotent(
    client: AsyncClient, alertmanager_payload: dict, test_db: AsyncIOMotorDatabase
) -> None:
    first = await _post(client, alertmanager_payload)
    second = await _post(client, alertmanager_payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert await test_db[COLL].count_documents({"source": "alertmanager"}) == 1
