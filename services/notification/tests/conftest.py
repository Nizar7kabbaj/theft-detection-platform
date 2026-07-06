from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from testcontainers.mongodb import MongoDbContainer

from app.migrations.runner import _run
from app.repositories.dead_letter import DeadLetterRepository
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.shared.config import settings
from app.shared.schemas.delivery import DeliveryIntentCreate, DeliverySource


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer("mongo:7") as container:
        yield container.get_connection_url()


def _point_settings_at(mongo_uri: str, db_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MONGODB_URL_LOCAL", mongo_uri)
    monkeypatch.setattr(settings, "DATABASE_NAME", db_name)


@pytest.fixture
async def test_db(
    mongo_uri: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncIOMotorDatabase]:
    db_name = f"test_{uuid.uuid4().hex}"
    _point_settings_at(mongo_uri, db_name, monkeypatch)
    await _run("up", None)
    client: AsyncIOMotorClient = AsyncIOMotorClient(mongo_uri)
    try:
        yield client[db_name]
    finally:
        await client.drop_database(db_name)
        client.close()


@pytest.fixture
async def raw_db(
    mongo_uri: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncIOMotorDatabase]:
    db_name = f"raw_{uuid.uuid4().hex}"
    _point_settings_at(mongo_uri, db_name, monkeypatch)
    client: AsyncIOMotorClient = AsyncIOMotorClient(mongo_uri)
    try:
        yield client[db_name]
    finally:
        await client.drop_database(db_name)
        client.close()


@pytest.fixture
def intent_repo(test_db: AsyncIOMotorDatabase) -> DeliveryIntentRepository:
    return DeliveryIntentRepository(test_db[settings.DELIVERY_INTENT_COLLECTION])


@pytest.fixture
def dlq_repo(test_db: AsyncIOMotorDatabase) -> DeadLetterRepository:
    return DeadLetterRepository(test_db[settings.DEAD_LETTER_COLLECTION])


@pytest.fixture
def alert_payload() -> dict:
    return {
        "alert_id": "a-1",
        "session_id": 123,
        "occurred_at": "2026-06-18T00:00:00Z",
        "camera_id": "cam-1",
        "severity": "SEVERITY_CRITICAL",
        "alert_type": "ALERT_TYPE_BENDING",
    }


@pytest.fixture
def alertmanager_payload() -> dict:
    return {
        "version": "4",
        "groupKey": '{}:{alertname="BackendHighErrorRate"}',
        "status": "firing",
        "receiver": "notification-service-webhook",
        "groupLabels": {"alertname": "BackendHighErrorRate"},
        "commonLabels": {"alertname": "BackendHighErrorRate", "severity": "critical"},
        "commonAnnotations": {"summary": "error rate above threshold"},
        "externalURL": "http://localhost:9093",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "BackendHighErrorRate", "severity": "critical"},
                "annotations": {"summary": "error rate above threshold"},
                "startsAt": "2026-06-18T00:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://localhost:9090/graph",
                "fingerprint": "abc123",
            }
        ],
    }


@pytest.fixture
def make_create(alert_payload: dict) -> Callable[..., DeliveryIntentCreate]:
    def _make(**overrides: object) -> DeliveryIntentCreate:
        data: dict = {
            "source": DeliverySource.ALERT,
            "source_ref": "ref-1",
            "recipient": "123456",
            "payload": dict(alert_payload),
        }
        data.update(overrides)
        return DeliveryIntentCreate(**data)

    return _make


@pytest.fixture
def age_doc(test_db: AsyncIOMotorDatabase) -> Callable[..., object]:
    async def _age(
        collection: str, intent_id: str, updated_at: datetime, **extra: object
    ) -> None:
        changes: dict = {"updated_at": updated_at}
        changes.update(extra)
        await test_db[collection].update_one(
            {"_id": ObjectId(intent_id)}, {"$set": changes}
        )

    return _age
