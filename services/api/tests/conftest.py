from datetime import UTC
from pathlib import Path
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

    async def list_page(
        self,
        severity: str | None = None,
        acknowledged: bool | None = None,
        decision: str | None = None,
        camera_id: str | None = None,
        sort: str = "created_at",
        limit: int = 51,
        after: tuple[Any, str] | None = None,
        start: Any = None,
        end: Any = None,
    ) -> list[dict[str, Any]]:
        field = "decided_at" if sort == "decided_at" else "created_at"
        docs = list(self.store.values())
        if severity:
            docs = [d for d in docs if d.get("severity") == severity]
        if acknowledged is not None:
            docs = [d for d in docs if bool(d.get("acknowledged", False)) is acknowledged]
        if decision:
            docs = [d for d in docs if d.get("decision") == decision]
        if camera_id:
            docs = [d for d in docs if d.get("camera_id") == camera_id]
        docs = [d for d in docs if d.get(field) is not None]
        if start is not None:
            docs = [d for d in docs if d[field] >= start]
        if end is not None:
            docs = [d for d in docs if d[field] <= end]
        docs.sort(key=lambda d: (d[field], str(d["_id"])), reverse=True)
        if after is not None:
            boundary, id_ = after
            docs = [d for d in docs if (d[field], str(d["_id"])) < (boundary, id_)]
        return docs[:limit]

    async def acknowledge(self, id_: str) -> tuple[dict[str, Any] | None, bool]:
        doc = self.store.get(id_)
        if doc is None:
            return None, False
        if doc.get("acknowledged") is True:
            return doc, False
        doc["acknowledged"] = True
        return doc, True

    async def get(self, id_: str) -> dict[str, Any] | None:
        return self.store.get(id_)

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
def mock_audit_client(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def alert_usecase(fake_alert_repo, mock_redis, mock_alert_client, mock_audit_client):
    from app.usecases.alert_usecase import AlertUseCase

    return AlertUseCase(
        repo=fake_alert_repo,
        redis=mock_redis,
        alert_client=mock_alert_client,
        audit_client=mock_audit_client,
    )


@pytest.fixture
def sample_alert_doc() -> dict[str, Any]:
    from datetime import datetime

    return {
        "_id": "oid-1",
        "alert_id": "a1",
        "session_id": 1,
        "occurred_at": datetime(2026, 6, 12, 10, 0, tzinfo=UTC),
        "camera_id": "cam-1",
        "severity": "SEVERITY_WARNING",
        "object": {"class_name": "phone", "confidence": 0.92},
        "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        "snapshot_path": "snaps/a1.jpg",
    }


class FakeCameraRepo:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self._next_id = 1
        self._names: set[str] = set()

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        from pymongo.errors import DuplicateKeyError

        name = data.get("name")
        if name in self._names:
            raise DuplicateKeyError(f"duplicate name {name}")
        oid = f"oid-{self._next_id}"
        self._next_id += 1
        doc = {**data, "_id": oid}
        self.store[oid] = doc
        if name:
            self._names.add(name)
        return doc

    async def get(self, id_: str) -> dict[str, Any] | None:
        return self.store.get(id_)

    async def list(
        self, query: dict[str, Any] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return list(self.store.values())[:limit]

    async def delete(self, id_: str) -> bool:
        doc = self.store.pop(id_, None)
        if doc is None:
            return False
        self._names.discard(doc.get("name"))
        return True


@pytest.fixture
def fake_camera_repo() -> FakeCameraRepo:
    return FakeCameraRepo()


@pytest.fixture
def mock_stream(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def camera_usecase(fake_camera_repo, mock_redis, mock_stream):
    from app.usecases.camera_usecase import CameraUseCase

    return CameraUseCase(repo=fake_camera_repo, redis=mock_redis, stream=mock_stream)


@pytest.fixture
def sample_camera_doc() -> dict[str, Any]:
    from datetime import datetime

    return {
        "_id": "oid-cam-1",
        "camera_id": "cam-a",
        "name": "front-door",
        "location": "entrance",
        "stream_url": "rtsp://cam-1/stream",
        "status": "active",
        "created_at": datetime(2026, 6, 12, 10, 0, tzinfo=UTC),
    }


class FakeStatsRepo:
    def __init__(self) -> None:
        self.counts = {
            "alerts": 0,
            "detections": 0,
            "cameras": 0,
            "alerts_today": 0,
            "SEVERITY_WARNING": 0,
            "SEVERITY_NOTICE": 0,
        }
        self.top: list[dict[str, Any]] = []

    async def count_alerts(self) -> int:
        return self.counts["alerts"]

    async def count_detections(self) -> int:
        return self.counts["detections"]

    async def count_cameras(self) -> int:
        return self.counts["cameras"]

    async def count_alerts_today(self) -> int:
        return self.counts["alerts_today"]

    async def count_by_severity(self, severities: list[str]) -> int:
        return sum(self.counts.get(name, 0) for name in severities)

    async def top_objects(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.top[:limit]


@pytest.fixture
def fake_stats_repo() -> FakeStatsRepo:
    return FakeStatsRepo()


@pytest.fixture
def stats_usecase(fake_stats_repo, mock_redis):
    from app.usecases.stats_usecase import StatsUseCase

    return StatsUseCase(repo=fake_stats_repo, redis=mock_redis)


def pytest_collection_modifyitems(config, items):
    integration_dir = Path(__file__).parent / "integration"
    for item in items:
        marker = "integration" if integration_dir in Path(item.fspath).parents else "unit"
        item.add_marker(getattr(pytest.mark, marker))
