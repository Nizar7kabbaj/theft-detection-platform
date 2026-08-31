from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.repositories.audit_outbox_repository import AuditOutboxRepository, PendingEvent

_PAST = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _enqueue(session, event_id: str | None = None, payload: bytes = b"event-bytes") -> str:
    identifier = event_id or str(uuid.uuid4())
    await AuditOutboxRepository(session).enqueue(identifier, payload, _PAST)
    await session.commit()
    return identifier


async def test_enqueue_makes_the_event_claimable(db_session):
    event_id = await _enqueue(db_session)
    claimed = await AuditOutboxRepository(db_session).claim(10)

    assert [entry.event_id for entry in claimed] == [event_id]


async def test_claimed_event_carries_payload_and_defaults(db_session):
    await _enqueue(db_session, payload=b"\x00\x01\x02")
    claimed = await AuditOutboxRepository(db_session).claim(1)
    pending = claimed[0]

    assert isinstance(pending, PendingEvent)
    assert pending.event_bytes == b"\x00\x01\x02"
    assert pending.attempts == 0
    assert pending.occurred_at == _PAST
    assert pending.created_at is not None


async def test_duplicate_event_id_is_rejected(db_session):
    event_id = await _enqueue(db_session)

    with pytest.raises(IntegrityError):
        await AuditOutboxRepository(db_session).enqueue(event_id, b"other", _PAST)


async def test_claim_respects_the_limit(db_session):
    for _ in range(5):
        await _enqueue(db_session)

    assert len(await AuditOutboxRepository(db_session).claim(2)) == 2


async def test_claim_returns_events_in_insertion_order(db_session):
    first = await _enqueue(db_session)
    second = await _enqueue(db_session)
    claimed = await AuditOutboxRepository(db_session).claim(10)

    assert [entry.event_id for entry in claimed] == [first, second]


async def test_claim_on_empty_outbox_returns_nothing(db_session):
    assert await AuditOutboxRepository(db_session).claim(10) == []


async def test_release_deletes_the_event(db_session):
    await _enqueue(db_session)
    repo = AuditOutboxRepository(db_session)
    pending = (await repo.claim(1))[0]

    await repo.release(pending.id)
    await db_session.commit()

    assert await repo.pending_count() == 0


async def test_defer_increments_attempts_and_hides_the_event(db_session):
    await _enqueue(db_session)
    repo = AuditOutboxRepository(db_session)
    pending = (await repo.claim(1))[0]

    await repo.defer(pending.id, datetime.now(UTC) + timedelta(hours=1))
    await db_session.commit()

    assert await repo.claim(10) == []
    assert await repo.pending_count() == 1


async def test_deferred_event_returns_when_due(db_session):
    await _enqueue(db_session)
    repo = AuditOutboxRepository(db_session)
    pending = (await repo.claim(1))[0]

    await repo.defer(pending.id, datetime.now(UTC) - timedelta(seconds=1))
    await db_session.commit()

    reclaimed = await repo.claim(10)
    assert len(reclaimed) == 1
    assert reclaimed[0].attempts == 1


async def test_bury_moves_the_event_to_dead_letter(db_session):
    event_id = await _enqueue(db_session)
    repo = AuditOutboxRepository(db_session)
    pending = (await repo.claim(1))[0]

    await repo.bury(pending, 3)
    await db_session.commit()

    assert await repo.pending_count() == 0
    result = await db_session.execute(
        text("select event_id, last_status, attempts from audit_outbox_dead")
    )
    row = result.one()
    assert str(row[0]) == event_id
    assert row[1] == 3
    assert row[2] == pending.attempts + 1


async def test_bury_preserves_payload_and_created_at(db_session):
    await _enqueue(db_session, payload=b"\xff\xfe")
    repo = AuditOutboxRepository(db_session)
    pending = (await repo.claim(1))[0]

    await repo.bury(pending, 2)
    await db_session.commit()

    result = await db_session.execute(
        text("select event_bytes, created_at, occurred_at from audit_outbox_dead")
    )
    row = result.one()
    assert bytes(row[0]) == b"\xff\xfe"
    assert row[1] == pending.created_at
    assert row[2] == _PAST


async def test_pending_count_tracks_the_queue(db_session):
    repo = AuditOutboxRepository(db_session)

    assert await repo.pending_count() == 0
    await _enqueue(db_session)
    await _enqueue(db_session)

    assert await repo.pending_count() == 2


async def test_oldest_pending_age_is_zero_when_empty(db_session):
    assert await AuditOutboxRepository(db_session).oldest_pending_age_seconds() == 0.0


async def test_oldest_pending_age_is_positive_with_backlog(db_session):
    await _enqueue(db_session)

    assert await AuditOutboxRepository(db_session).oldest_pending_age_seconds() >= 0.0


async def test_concurrent_claims_never_return_the_same_event(db_engine):
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    async with factory() as seed:
        for _ in range(2):
            await AuditOutboxRepository(seed).enqueue(str(uuid.uuid4()), b"payload", _PAST)
        await seed.commit()

    async with factory() as first, factory() as second:
        first_claim = await AuditOutboxRepository(first).claim(1)
        second_claim = await AuditOutboxRepository(second).claim(1)

        assert len(first_claim) == 1
        assert len(second_claim) == 1
        assert first_claim[0].id != second_claim[0].id

        await first.rollback()
        await second.rollback()


async def test_locked_rows_are_skipped_when_no_others_remain(db_engine):
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    async with factory() as seed:
        await AuditOutboxRepository(seed).enqueue(str(uuid.uuid4()), b"payload", _PAST)
        await seed.commit()

    async with factory() as holder, factory() as other:
        held = await AuditOutboxRepository(holder).claim(1)
        assert len(held) == 1

        assert await AuditOutboxRepository(other).claim(1) == []

        await holder.rollback()
        await other.rollback()
