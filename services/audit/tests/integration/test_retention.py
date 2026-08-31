from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.chain import GENESIS_CHECKPOINT_HASH
from app.core.config import get_settings
from app.core.signing import build_checkpoint_payload, get_signer
from app.repositories.audit_repository import AuditRepository
from app.services.retention import RetentionError, RetentionService, retention_cutoff
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


async def seed_aged(session, count: int = 12, oldest_age_days: int = 500) -> None:
    base = datetime.now(UTC) - timedelta(days=oldest_age_days)
    for index in range(count):
        await append_one(
            session,
            actor=f"actor-{index % 3}",
            occurred_at=base + timedelta(days=index * 10),
        )
    await session.execute(text("SET LOCAL audit.maintenance = 'on'"))


async def backdate_persisted(session, oldest_age_days: int = 500) -> None:
    base = datetime.now(UTC) - timedelta(days=oldest_age_days)
    await session.execute(
        text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_events_no_update")
    )
    rows = (
        (
            await session.execute(
                text("SELECT sequence_number FROM audit_events ORDER BY sequence_number ASC")
            )
        )
        .scalars()
        .all()
    )
    for offset, sequence_number in enumerate(rows):
        await session.execute(
            text("UPDATE audit_events SET persisted_at = :p WHERE sequence_number = :s"),
            {"p": base + timedelta(days=offset * 10), "s": sequence_number},
        )
    await session.execute(
        text("ALTER TABLE audit_events ENABLE TRIGGER trg_audit_events_no_update")
    )
    await session.commit()


async def checkpoint_through(session, tail_sequence_number: int) -> int:
    events = AuditRepository(session)
    signer = get_signer()
    row = await events.event_at(tail_sequence_number)
    payload = build_checkpoint_payload(
        key_id=signer.key_id,
        tree_size=tail_sequence_number,
        tail_sequence_number=tail_sequence_number,
        tail_chain_hash=row.chain_hash,
        prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
        signature_algorithm=signer.signature_algorithm,
    )
    created = await events.append_checkpoint(
        tail_sequence_number=tail_sequence_number,
        tail_chain_hash=row.chain_hash,
        tree_size=tail_sequence_number,
        signature=signer.sign(payload),
        key_id=signer.key_id,
        prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
        payload=payload,
        signature_algorithm=signer.signature_algorithm,
    )
    await session.commit()
    return created.checkpoint_id


def test_the_cutoff_is_the_retention_window_ago() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    expected = now - timedelta(days=get_settings().retention_days)
    assert retention_cutoff(now) == expected


async def test_a_fresh_log_has_nothing_to_seal(app_session, owner_session) -> None:
    for _ in range(5):
        await append_one(app_session)
    assert await RetentionService(owner_session).next_segment() is None


async def test_an_empty_log_has_nothing_to_seal(owner_session) -> None:
    assert await RetentionService(owner_session).next_segment() is None


async def test_an_aged_log_offers_a_segment(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    candidate = await RetentionService(owner_session).next_segment()
    assert candidate is not None
    assert candidate.first_sequence_number == 1


async def test_the_candidate_covers_only_the_window(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    candidate = await RetentionService(owner_session).next_segment()
    assert (
        candidate.row_count == candidate.last_sequence_number - candidate.first_sequence_number + 1
    )
    assert candidate.last_sequence_number < 12


async def test_the_candidate_carries_the_terminal_hash(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    candidate = await RetentionService(owner_session).next_segment()
    row = await AuditRepository(owner_session).event_at(candidate.last_sequence_number)
    assert candidate.terminal_chain_hash == row.chain_hash


async def test_sealing_drops_the_rows(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, candidate.last_sequence_number)
    outcome = await service.seal_and_drop(candidate)
    await owner_session.commit()
    remaining = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert remaining == 12 - outcome.row_count


async def test_sealing_writes_a_segment(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, candidate.last_sequence_number)
    await service.seal_and_drop(candidate)
    await owner_session.commit()
    count = (
        await app_session.execute(text("SELECT count(*) FROM audit_chain_segments"))
    ).scalar_one()
    assert count == 1


async def test_the_chain_still_verifies_after_sealing(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, candidate.last_sequence_number)
    await service.seal_and_drop(candidate)
    await owner_session.commit()
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True


async def test_the_survivor_links_to_the_sealed_terminal_hash(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, candidate.last_sequence_number)
    outcome = await service.seal_and_drop(candidate)
    await owner_session.commit()
    survivor = (
        await app_session.execute(
            text("SELECT prev_hash FROM audit_events ORDER BY sequence_number ASC LIMIT 1")
        )
    ).scalar_one()
    assert bytes(survivor) == outcome.terminal_chain_hash


async def test_sealing_is_refused_beyond_the_latest_checkpoint(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, 1)
    with pytest.raises(RetentionError, match="does not cover"):
        await service.seal_and_drop(candidate)
    await owner_session.rollback()


async def test_a_refused_seal_drops_nothing(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    await checkpoint_through(owner_session, 1)
    with pytest.raises(RetentionError):
        await service.seal_and_drop(candidate)
    await owner_session.rollback()
    remaining = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert remaining == 12


async def test_sealing_without_any_checkpoint_is_allowed(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    outcome = await service.seal_and_drop(candidate)
    await owner_session.commit()
    assert outcome.checkpoint_id is None


async def test_a_second_seal_starts_after_the_first_segment(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    first = await service.next_segment()
    await service.seal_and_drop(first)
    await owner_session.commit()
    second = await RetentionService(owner_session).next_segment()
    if second is not None:
        assert second.first_sequence_number > first.last_sequence_number


async def test_verification_after_two_seals_still_holds(app_session, owner_session) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    service = RetentionService(owner_session)
    first = await service.next_segment()
    await service.seal_and_drop(first)
    await owner_session.commit()
    second = await RetentionService(owner_session).next_segment()
    if second is not None:
        await RetentionService(owner_session).seal_and_drop(second)
        await owner_session.commit()
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True


async def test_the_tail_state_uses_the_segment_when_the_log_is_emptied(
    app_session, owner_session
) -> None:
    await seed_aged(app_session)
    await backdate_persisted(owner_session)
    segment_terminal = None
    service = RetentionService(owner_session)
    candidate = await service.next_segment()
    outcome = await service.seal_and_drop(candidate)
    await owner_session.commit()
    segment_terminal = outcome.terminal_chain_hash
    row = (
        await app_session.execute(
            text(
                "SELECT terminal_chain_hash FROM audit_chain_segments "
                "ORDER BY last_sequence_number DESC LIMIT 1"
            )
        )
    ).scalar_one()
    assert bytes(row) == segment_terminal
