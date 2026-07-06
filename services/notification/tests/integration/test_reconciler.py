from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace

from app.shared.config import settings
from app.shared.schemas.delivery import DeliveryStatus
from app.worker import tasks

pytestmark = pytest.mark.integration

COLL = settings.DELIVERY_INTENT_COLLECTION
tracer = trace.get_tracer("test")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _call(intent, cutoff, intent_repo, dlq_repo) -> str:
    with tracer.start_as_current_span("sweep") as span:
        return await tasks._requeue_one(intent, cutoff, intent_repo, dlq_repo, span)


async def test_retires_poison(
    intent_repo, dlq_repo, make_create, age_doc, monkeypatch
) -> None:
    apply = MagicMock()
    monkeypatch.setattr(tasks.send_alert_task, "apply_async", apply)
    seed = await intent_repo.acquire(make_create())
    await age_doc(
        COLL, seed.id, _now() - timedelta(minutes=10), requeue_count=3
    )
    intent = await intent_repo.get_by_id(seed.id)

    outcome = await _call(intent, _now() - timedelta(minutes=1), intent_repo, dlq_repo)

    assert outcome == "poison"
    refetched = await intent_repo.get_by_id(seed.id)
    assert refetched.status == DeliveryStatus.DEAD
    assert await dlq_repo.find_by_intent_id(seed.id) is not None
    apply.assert_not_called()


async def test_requeues_stale(
    intent_repo, dlq_repo, make_create, age_doc, monkeypatch
) -> None:
    apply = MagicMock()
    monkeypatch.setattr(tasks.send_alert_task, "apply_async", apply)
    seed = await intent_repo.acquire(make_create())
    await age_doc(COLL, seed.id, _now() - timedelta(minutes=10))
    intent = await intent_repo.get_by_id(seed.id)

    outcome = await _call(intent, _now() - timedelta(minutes=1), intent_repo, dlq_repo)

    assert outcome == "requeued"
    refetched = await intent_repo.get_by_id(seed.id)
    assert refetched.status == DeliveryStatus.PENDING
    assert refetched.requeue_count == 1
    apply.assert_called_once_with(args=[seed.id])


async def test_races_on_fresh(
    intent_repo, dlq_repo, make_create, age_doc, monkeypatch
) -> None:
    apply = MagicMock()
    monkeypatch.setattr(tasks.send_alert_task, "apply_async", apply)
    seed = await intent_repo.acquire(make_create())
    await age_doc(COLL, seed.id, _now())
    intent = await intent_repo.get_by_id(seed.id)

    outcome = await _call(intent, _now() - timedelta(minutes=1), intent_repo, dlq_repo)

    assert outcome == "raced"
    apply.assert_not_called()
