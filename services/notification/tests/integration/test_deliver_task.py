from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from bson import ObjectId

from app.shared.recipient import UNCONFIGURED_RECIPIENT
from app.shared.schemas.delivery import DeliveryStatus
from app.worker import tasks

pytestmark = pytest.mark.integration


async def test_marks_sent_on_success(intent_repo, dlq_repo, make_create, monkeypatch) -> None:
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(tasks, "_dispatch", dispatch)
    intent = await intent_repo.acquire(make_create())

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["delivered"] is True
    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.SENT
    assert refetched.attempts == 1
    assert await dlq_repo.find_by_intent_id(intent.id) is None
    dispatch.assert_called_once()


async def test_dead_on_decline(intent_repo, dlq_repo, make_create, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "_dispatch", MagicMock(return_value=False))
    intent = await intent_repo.acquire(make_create())

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["reason"] == "declined"
    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.DEAD
    assert await dlq_repo.find_by_intent_id(intent.id) is not None


async def test_retry_on_transport_error_non_final(
    intent_repo, dlq_repo, make_create, monkeypatch
) -> None:
    monkeypatch.setattr(
        tasks,
        "_dispatch",
        MagicMock(side_effect=requests.exceptions.RequestException("net")),
    )
    intent = await intent_repo.acquire(make_create())

    with pytest.raises(requests.exceptions.RequestException):
        await tasks._deliver(intent.id, final_attempt=False)

    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.FAILED
    assert refetched.attempts == 1
    assert await dlq_repo.find_by_intent_id(intent.id) is None


async def test_dead_on_transport_error_final(
    intent_repo, dlq_repo, make_create, monkeypatch
) -> None:
    monkeypatch.setattr(
        tasks,
        "_dispatch",
        MagicMock(side_effect=requests.exceptions.RequestException("net")),
    )
    intent = await intent_repo.acquire(make_create())

    result = await tasks._deliver(intent.id, final_attempt=True)

    assert result["reason"] == "dead"
    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.DEAD
    assert await dlq_repo.find_by_intent_id(intent.id) is not None


async def test_dead_on_render_failure(intent_repo, dlq_repo, make_create, monkeypatch) -> None:
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(tasks, "_dispatch", dispatch)
    broken = {"session_id": 1, "occurred_at": "2026-06-18T00:00:00Z"}
    intent = await intent_repo.acquire(make_create(payload=broken))

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["reason"] == "render"
    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.DEAD
    assert await dlq_repo.find_by_intent_id(intent.id) is not None
    dispatch.assert_not_called()


async def test_dead_on_unconfigured_recipient(
    intent_repo, dlq_repo, make_create, monkeypatch
) -> None:
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(tasks, "_dispatch", dispatch)
    intent = await intent_repo.acquire(make_create(recipient=UNCONFIGURED_RECIPIENT))

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["reason"] == "unconfigured"
    refetched = await intent_repo.get_by_id(intent.id)
    assert refetched.status == DeliveryStatus.DEAD
    assert await dlq_repo.find_by_intent_id(intent.id) is not None
    dispatch.assert_not_called()


async def test_skips_already_sent(intent_repo, make_create, monkeypatch) -> None:
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(tasks, "_dispatch", dispatch)
    intent = await intent_repo.acquire(make_create())
    await intent_repo.mark_sent(intent.id)

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["reason"] == "already_sent"
    dispatch.assert_not_called()


async def test_drops_missing_intent(test_db, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "_dispatch", MagicMock(return_value=True))
    result = await tasks._deliver(str(ObjectId()), final_attempt=False)
    assert result["reason"] == "missing"


async def test_not_claimed_on_dead(intent_repo, make_create, monkeypatch) -> None:
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(tasks, "_dispatch", dispatch)
    intent = await intent_repo.acquire(make_create())
    await intent_repo.mark_dead(intent.id, "x")

    result = await tasks._deliver(intent.id, final_attempt=False)

    assert result["reason"] == "not_claimed"
    dispatch.assert_not_called()
