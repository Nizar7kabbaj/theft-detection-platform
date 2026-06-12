from typing import Any

import pytest


class FakeAlertRepo:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        oid = f"oid-{self._next_id}"
        self._next_id += 1
        doc = {**data, "_id": oid}
        self.store[oid] = doc
        return doc

    async def list_filtered(
        self,
        severity: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        docs = list(self.store.values())
        if severity:
            docs = [d for d in docs if d.get("severity") == severity.upper()]
        docs.sort(key=lambda d: d.get("created_at"), reverse=True)
        return docs[skip : skip + limit]

    async def acknowledge(self, id_: str) -> dict[str, Any] | None:
        if id_ not in self.store:
            return None
        self.store[id_]["acknowledged"] = True
        return self.store[id_]

    async def delete(self, id_: str) -> bool:
        return self.store.pop(id_, None) is not None


@pytest.fixture
def fake_alert_repo() -> FakeAlertRepo:
    return FakeAlertRepo()


@pytest.fixture
def mock_redis(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def mock_alert_client(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def alert_usecase(fake_alert_repo, mock_redis, mock_alert_client):
    from app.usecases.alert_usecase import AlertUseCase

    return AlertUseCase(
        repo=fake_alert_repo,
        redis=mock_redis,
        alert_client=mock_alert_client,
    )


@pytest.fixture
def sample_alert_doc() -> dict[str, Any]:
    return {
        "_id": "oid-1",
        "alert_id": "a1",
        "session_id": 1,
        "timestamp": "2026-06-12T10:00:00Z",
        "camera_id": "cam-1",
        "severity": "HIGH",
        "object": {"class_name": "phone", "confidence": 0.92},
        "alert_type": "object_proximity",
        "snapshot_path": "snaps/a1.jpg",
    }
