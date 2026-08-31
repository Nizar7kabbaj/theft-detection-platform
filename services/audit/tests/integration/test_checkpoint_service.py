from __future__ import annotations

import asyncio
import logging

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core import database as database_module
from app.core.chain import GENESIS_CHECKPOINT_HASH, compute_checkpoint_hash
from app.core.config import get_settings
from app.core.signing import build_checkpoint_payload
from app.repositories.audit_repository import VERIFY_FAILURE_NONE, AuditRepository
from app.services.checkpoint_service import (
    checkpoint_loop,
    create_checkpoint,
    verify_checkpoints,
)
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def dispose_app_engine(database_settings: None):
    yield
    await database_module.dispose_engine()


async def seed(session, count: int = 5) -> None:
    for index in range(count):
        await append_one(session, actor=f"actor-{index}")


async def test_an_empty_log_produces_no_checkpoint(app_session) -> None:
    assert await create_checkpoint() is None


async def test_a_checkpoint_is_written_over_a_seeded_chain(app_session) -> None:
    await seed(app_session)
    assert await create_checkpoint() == 1


async def test_the_checkpoint_lands_in_the_table(app_session) -> None:
    await seed(app_session)
    await create_checkpoint()
    count = (await app_session.execute(text("SELECT count(*) FROM audit_checkpoints"))).scalar_one()
    assert count == 1


async def test_the_checkpoint_binds_the_tail_of_the_chain(app_session) -> None:
    await seed(app_session)
    checkpoint_id = await create_checkpoint()
    events = AuditRepository(app_session)
    tail = await events.tail_state()
    row = await events.checkpoint_by_id(checkpoint_id)
    assert row.tail_sequence_number == tail.tail_sequence_number
    assert row.tail_chain_hash == tail.prev_hash
    assert row.tree_size == tail.tree_size


async def test_the_first_checkpoint_links_to_genesis(app_session) -> None:
    await seed(app_session)
    checkpoint_id = await create_checkpoint()
    row = await AuditRepository(app_session).checkpoint_by_id(checkpoint_id)
    assert row.prev_checkpoint_hash == GENESIS_CHECKPOINT_HASH


async def test_the_checkpoint_carries_the_active_key_id(app_session) -> None:
    await seed(app_session)
    checkpoint_id = await create_checkpoint()
    row = await AuditRepository(app_session).checkpoint_by_id(checkpoint_id)
    assert row.key_id == get_settings().checkpoint_key_id


async def test_the_checkpoint_signature_is_ed25519_sized(app_session) -> None:
    await seed(app_session)
    checkpoint_id = await create_checkpoint()
    row = await AuditRepository(app_session).checkpoint_by_id(checkpoint_id)
    assert row.signature_algorithm == 1
    assert len(row.signature) == 64


async def test_the_checkpoint_hash_matches_its_payload(app_session) -> None:
    await seed(app_session)
    checkpoint_id = await create_checkpoint()
    row = await AuditRepository(app_session).checkpoint_by_id(checkpoint_id)
    payload = build_checkpoint_payload(
        key_id=row.key_id,
        tree_size=row.tree_size,
        tail_sequence_number=row.tail_sequence_number,
        tail_chain_hash=row.tail_chain_hash,
        prev_checkpoint_hash=row.prev_checkpoint_hash,
        signature_algorithm=row.signature_algorithm,
        hash_algorithm=row.hash_algorithm,
    )
    assert row.checkpoint_hash == compute_checkpoint_hash(payload, row.hash_algorithm)


async def test_the_written_signature_verifies(app_session) -> None:
    await seed(app_session)
    await create_checkpoint()
    result = await verify_checkpoints(AuditRepository(app_session))
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.checkpoints_verified == 1


async def test_a_second_checkpoint_without_new_events_is_skipped(app_session) -> None:
    await seed(app_session)
    await create_checkpoint()
    assert await create_checkpoint() is None


async def test_new_events_allow_a_second_checkpoint(app_session) -> None:
    await seed(app_session)
    first = await create_checkpoint()
    await seed(app_session, count=3)
    second = await create_checkpoint()
    assert second is not None
    assert second != first


async def test_the_second_checkpoint_links_to_the_first(app_session) -> None:
    await seed(app_session)
    first = await create_checkpoint()
    await seed(app_session, count=3)
    second = await create_checkpoint()
    events = AuditRepository(app_session)
    earlier = await events.checkpoint_by_id(first)
    later = await events.checkpoint_by_id(second)
    assert later.prev_checkpoint_hash == earlier.checkpoint_hash


async def test_a_chain_of_checkpoints_verifies(app_session) -> None:
    for _ in range(3):
        await seed(app_session, count=2)
        await create_checkpoint()
    result = await verify_checkpoints(AuditRepository(app_session))
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.checkpoints_verified == 3


async def test_the_latest_checkpoint_is_the_newest(app_session) -> None:
    await seed(app_session)
    await create_checkpoint()
    await seed(app_session, count=2)
    second = await create_checkpoint()
    latest = await AuditRepository(app_session).latest_checkpoint()
    assert latest.checkpoint_id == second


async def test_the_tree_size_grows_with_the_log(app_session) -> None:
    await seed(app_session, count=4)
    first = await create_checkpoint()
    await seed(app_session, count=3)
    second = await create_checkpoint()
    events = AuditRepository(app_session)
    assert (await events.checkpoint_by_id(first)).tree_size == 4
    assert (await events.checkpoint_by_id(second)).tree_size == 7


async def test_the_loop_writes_a_checkpoint(app_session) -> None:
    await seed(app_session)
    stop = asyncio.Event()
    task = asyncio.create_task(checkpoint_loop(stop))
    await asyncio.sleep(1.4)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    count = (await app_session.execute(text("SELECT count(*) FROM audit_checkpoints"))).scalar_one()
    assert count == 1


async def test_the_loop_stops_when_asked(app_session) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(checkpoint_loop(stop))
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert task.done() is True


async def test_the_loop_writes_nothing_for_an_empty_log(app_session) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(checkpoint_loop(stop))
    await asyncio.sleep(1.4)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    count = (await app_session.execute(text("SELECT count(*) FROM audit_checkpoints"))).scalar_one()
    assert count == 0


async def test_the_loop_survives_a_failing_cycle(
    app_session, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    await seed(app_session)

    async def broken() -> int | None:
        raise RuntimeError("checkpoint store unreachable")

    monkeypatch.setattr("app.services.checkpoint_service.create_checkpoint", broken)
    stop = asyncio.Event()
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(checkpoint_loop(stop))
        await asyncio.sleep(1.4)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
    assert task.exception() is None
    assert any("checkpoint cycle failed" in record.message for record in caplog.records)


async def test_a_checkpoint_survives_its_tail_row_being_sealed_away(
    app_session, owner_session
) -> None:
    await seed(app_session, count=5)
    await create_checkpoint()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DELETE FROM audit_events WHERE sequence_number = 5"))
    await owner_session.commit()
    result = await verify_checkpoints(AuditRepository(app_session))
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.checkpoints_verified == 1


async def test_a_checkpoint_still_binds_a_tail_row_that_remains(app_session, owner_session) -> None:
    await seed(app_session, count=5)
    await create_checkpoint()
    await owner_session.execute(
        text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_events_no_update")
    )
    await owner_session.execute(
        text("UPDATE audit_events SET chain_hash = :h WHERE sequence_number = 5"),
        {"h": bytes(range(32))},
    )
    result = await verify_checkpoints(AuditRepository(owner_session))
    await owner_session.rollback()
    assert result.failure_kind != VERIFY_FAILURE_NONE
