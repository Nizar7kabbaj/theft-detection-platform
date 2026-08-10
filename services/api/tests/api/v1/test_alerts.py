from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.v1.alerts import router as alerts_router
from app.core.authz import get_current_user
from app.core.errors import NotFoundError
from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_alert_usecase
from app.schemas.alert import AlertCreate, AlertResponse, Severity
from app.schemas.identity import CurrentUser


def _sample_response(alert_id: str = "a1") -> AlertResponse:
    return AlertResponse.model_validate(
        {
            "_id": "65f1a2b3c4d5e6f7a8b9c0d1",
            "alert_id": alert_id,
            "session_id": 1,
            "occurred_at": datetime.now(UTC),
            "camera_id": "cam-1",
            "severity": "SEVERITY_WARNING",
            "object_name": "person",
            "confidence": 0.9,
            "snapshot_url": None,
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
        }
    )


class FakeAlertUseCase:
    def __init__(self) -> None:
        self.create_calls: list[AlertCreate] = []
        self.list_calls: list[dict[str, Any]] = []
        self.acknowledge_calls: list[str] = []
        self.delete_calls: list[str] = []
        self._create_result: AlertResponse | None = None
        self._list_result: list[AlertResponse] = []
        self._acknowledge_result: AlertResponse | None = None
        self._acknowledge_raises: Exception | None = None
        self._delete_raises: Exception | None = None

    def set_create_result(self, response: AlertResponse) -> None:
        self._create_result = response

    def set_list_result(self, items: list[AlertResponse]) -> None:
        self._list_result = items

    def set_acknowledge_result(self, response: AlertResponse) -> None:
        self._acknowledge_result = response

    def set_acknowledge_raises(self, exc: Exception) -> None:
        self._acknowledge_raises = exc

    def set_delete_raises(self, exc: Exception) -> None:
        self._delete_raises = exc

    async def create(self, payload: AlertCreate) -> AlertResponse:
        self.create_calls.append(payload)
        assert self._create_result is not None
        return self._create_result

    async def list(
        self, severity: Severity | None = None, limit: int = 50, skip: int = 0
    ) -> list[AlertResponse]:
        self.list_calls.append({"severity": severity, "limit": limit, "skip": skip})
        return self._list_result

    async def acknowledge(self, alert_id: str) -> AlertResponse:
        self.acknowledge_calls.append(alert_id)
        if self._acknowledge_raises is not None:
            raise self._acknowledge_raises
        assert self._acknowledge_result is not None
        return self._acknowledge_result

    async def delete(self, alert_id: str) -> None:
        self.delete_calls.append(alert_id)
        if self._delete_raises is not None:
            raise self._delete_raises


def _make_idempotency_state(
    *, hit: bool = False, cached: dict[str, Any] | None = None
) -> IdempotencyState:
    return IdempotencyState(
        cached_response=cached if hit else None,
        store_key="idem:test" if hit or cached is not None else None,
        body_hash="x" * 64 if hit or cached is not None else None,
        redis=None,
    )


@pytest.fixture
def fake_usecase() -> FakeAlertUseCase:
    return FakeAlertUseCase()


@pytest.fixture
def idem_state() -> dict[str, IdempotencyState]:
    return {"state": _make_idempotency_state(hit=False)}


OPERATOR_USER = CurrentUser(
    user_id="65f1a2b3c4d5e6f7a8b9c0d2",
    username="operator-1",
    roles=frozenset({"operator"}),
    session_id="sess-1",
)


@pytest.fixture
def app(fake_usecase: FakeAlertUseCase, idem_state: dict[str, IdempotencyState]) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(alerts_router, prefix="/api/v1")

    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    test_app.add_exception_handler(NotFoundError, _not_found_handler)

    def _get_usecase() -> FakeAlertUseCase:
        return fake_usecase

    def _get_idem() -> IdempotencyState:
        return idem_state["state"]

    async def _get_user() -> CurrentUser:
        return OPERATOR_USER

    test_app.dependency_overrides[get_alert_usecase] = _get_usecase
    test_app.dependency_overrides[idempotency] = _get_idem
    test_app.dependency_overrides[get_current_user] = _get_user
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _alert_create_body() -> dict[str, Any]:
    return {
        "alert_id": "a1",
        "frame_index": 0,
        "person": {},
        "session_id": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "camera_id": "cam-1",
        "severity": "SEVERITY_WARNING",
        "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
    }


class TestCreate:
    async def test_creates_alert_when_no_idempotency_hit(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_create_result(_sample_response())

        resp = await client.post("/api/v1/alerts", json=_alert_create_body())

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["alert_id"] == "a1"
        assert len(fake_usecase.create_calls) == 1

    async def test_returns_cached_on_idempotency_hit(
        self,
        client: AsyncClient,
        fake_usecase: FakeAlertUseCase,
        idem_state: dict[str, IdempotencyState],
    ) -> None:
        cached_body = _sample_response("cached").model_dump(mode="json", by_alias=True)
        idem_state["state"] = _make_idempotency_state(hit=True, cached=cached_body)

        resp = await client.post("/api/v1/alerts", json=_alert_create_body())

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["alert_id"] == "cached"
        assert len(fake_usecase.create_calls) == 0

    async def test_returns_422_on_missing_required_field(self, client: AsyncClient) -> None:
        body = _alert_create_body()
        del body["alert_id"]

        resp = await client.post("/api/v1/alerts", json=body)

        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestList:
    async def test_returns_alerts(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_list_result([_sample_response("a1"), _sample_response("a2")])

        resp = await client.get("/api/v1/alerts")

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_passes_severity_filter_through(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_list_result([])

        resp = await client.get("/api/v1/alerts?severity=SEVERITY_WARNING&limit=10&skip=5")

        assert resp.status_code == 200
        assert fake_usecase.list_calls == [
            {"severity": Severity.SEVERITY_WARNING, "limit": 10, "skip": 5}
        ]


class TestAcknowledge:
    async def test_returns_updated_alert(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_acknowledge_result(_sample_response())

        resp = await client.patch("/api/v1/alerts/a1/acknowledge")

        assert resp.status_code == 200
        assert resp.json()["alert_id"] == "a1"
        assert fake_usecase.acknowledge_calls == ["a1"]

    async def test_returns_404_when_not_found(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_acknowledge_raises(NotFoundError("alert missing not found"))

        resp = await client.patch("/api/v1/alerts/missing/acknowledge")

        assert resp.status_code == 404


class TestDelete:
    async def test_returns_204_on_success(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        resp = await client.delete("/api/v1/alerts/a1")

        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert fake_usecase.delete_calls == ["a1"]

    async def test_returns_404_when_not_found(
        self, client: AsyncClient, fake_usecase: FakeAlertUseCase
    ) -> None:
        fake_usecase.set_delete_raises(NotFoundError("alert missing not found"))

        resp = await client.delete("/api/v1/alerts/missing")

        assert resp.status_code == 404
