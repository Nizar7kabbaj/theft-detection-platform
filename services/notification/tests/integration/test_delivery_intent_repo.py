from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.shared.config import settings
from app.shared.schemas.delivery import DeliveryStatus, TelegramMessageRef

pytestmark = pytest.mark.integration

COLL = settings.DELIVERY_INTENT_COLLECTION


def _now() -> datetime:
    return datetime.now(UTC)


async def test_acquire_persists_pending(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    assert intent.status == DeliveryStatus.PENDING
    assert intent.attempts == 0
    assert intent.requeue_count == 0


async def test_acquire_is_idempotent_on_natural_key(
    intent_repo, make_create, test_db: AsyncIOMotorDatabase
) -> None:
    first = await intent_repo.acquire(make_create())
    second = await intent_repo.acquire(make_create())
    assert first.id == second.id
    assert await test_db[COLL].count_documents({}) == 1


async def test_mark_sending_claims_pending(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    claimed = await intent_repo.mark_sending(intent.id)
    assert claimed is not None
    assert claimed.status == DeliveryStatus.SENDING
    assert claimed.attempt_started_at is not None


async def test_mark_sending_on_sent_returns_none(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    await intent_repo.mark_sent(intent.id)
    assert await intent_repo.mark_sending(intent.id) is None


async def test_mark_sending_on_dead_returns_none(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    await intent_repo.mark_dead(intent.id, "x")
    assert await intent_repo.mark_sending(intent.id) is None


async def test_mark_sent_increments_attempts(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    sent = await intent_repo.mark_sent(intent.id)
    assert sent is not None
    assert sent.status == DeliveryStatus.SENT
    assert sent.attempts == 1
    assert sent.attempt_started_at is None


async def test_mark_failed_increments_attempts(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    failed = await intent_repo.mark_failed(intent.id, "boom")
    assert failed is not None
    assert failed.status == DeliveryStatus.FAILED
    assert failed.attempts == 1
    assert failed.last_error == "boom"


async def test_mark_dead_does_not_increment_attempts(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    dead = await intent_repo.mark_dead(intent.id, "gone")
    assert dead is not None
    assert dead.status == DeliveryStatus.DEAD
    assert dead.attempts == 0


async def test_mark_requeued_promotes_stale(intent_repo, make_create, age_doc) -> None:
    intent = await intent_repo.acquire(make_create())
    await age_doc(COLL, intent.id, _now() - timedelta(minutes=10))
    cutoff = _now() - timedelta(minutes=1)
    requeued = await intent_repo.mark_requeued(intent.id, cutoff)
    assert requeued is not None
    assert requeued.status == DeliveryStatus.PENDING
    assert requeued.requeue_count == 1


async def test_mark_requeued_skips_fresh(intent_repo, make_create, age_doc) -> None:
    intent = await intent_repo.acquire(make_create())
    await age_doc(COLL, intent.id, _now())
    cutoff = _now() - timedelta(minutes=1)
    assert await intent_repo.mark_requeued(intent.id, cutoff) is None


async def test_mark_requeued_skips_sent(intent_repo, make_create, age_doc) -> None:
    intent = await intent_repo.acquire(make_create())
    await intent_repo.mark_sent(intent.id)
    await age_doc(COLL, intent.id, _now() - timedelta(minutes=10))
    cutoff = _now() - timedelta(minutes=1)
    assert await intent_repo.mark_requeued(intent.id, cutoff) is None


async def test_find_stale_returns_old_sending(intent_repo, make_create, age_doc) -> None:
    intent = await intent_repo.acquire(make_create())
    await age_doc(
        COLL,
        intent.id,
        _now() - timedelta(minutes=10),
        status=DeliveryStatus.SENDING.value,
    )
    cutoff = _now() - timedelta(minutes=1)
    stale = await intent_repo.find_stale(DeliveryStatus.SENDING, cutoff)
    assert [i.id for i in stale] == [intent.id]


async def test_find_stale_ignores_fresh_sending(intent_repo, make_create, age_doc) -> None:
    intent = await intent_repo.acquire(make_create())
    await age_doc(COLL, intent.id, _now(), status=DeliveryStatus.SENDING.value)
    cutoff = _now() - timedelta(minutes=1)
    assert await intent_repo.find_stale(DeliveryStatus.SENDING, cutoff) == []


async def test_mark_sent_stores_the_telegram_handle(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    handle = TelegramMessageRef(chat_id=-100, message_id=42, kind="video")
    sent = await intent_repo.mark_sent(intent.id, handle)
    assert sent is not None
    assert sent.telegram == handle
    stored = await intent_repo.get_by_id(intent.id)
    assert stored is not None
    assert stored.telegram == handle


async def test_mark_snapshot_sent_keeps_the_snapshot_handle(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    snapshot = TelegramMessageRef(chat_id=-100, message_id=41, kind="photo")
    await intent_repo.mark_snapshot_sent(intent.id, snapshot)
    stored = await intent_repo.get_by_id(intent.id)
    assert stored is not None
    assert stored.telegram_snapshot == snapshot


async def test_claim_display_refuses_an_older_notice(intent_repo, make_create) -> None:
    intent = await intent_repo.acquire(make_create())
    newer = datetime(2026, 10, 7, 11, 51, 43, tzinfo=UTC)
    older = newer - timedelta(seconds=3)
    assert await intent_repo.claim_display(intent.id, newer) is True
    assert await intent_repo.claim_display(intent.id, older) is False
    assert await intent_repo.claim_display(intent.id, newer) is True
