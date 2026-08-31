from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import database as database_module
from app.core.chain import genesis_prev_hash
from app.repositories.audit_repository import AuditRepository
from app.server.grpc_gen import audit_pb2, common_pb2
from tests.integration.test_append_chain import make_payload

pytestmark = pytest.mark.integration


LIFECYCLE_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number


async def append_through(factory, actor: str) -> int:
    async with factory() as session:
        result = await AuditRepository(session).append(
            event_id=str(uuid.uuid4()),
            occurred_at=datetime.now(UTC),
            source_service=common_pb2.SOURCE_SERVICE_AUTH,
            actor=actor,
            severity=common_pb2.SEVERITY_INFO,
            trace_id="",
            payload_kind=LIFECYCLE_KIND,
            schema_version=1,
            event_bytes=make_payload(actor=actor),
        )
        await session.commit()
        return result.sequence_number


@pytest.fixture
async def concurrent_factory(database_settings: None):
    engine = create_async_engine(database_module.resolve_app_url(), pool_size=10, max_overflow=0)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


async def test_parallel_appends_all_land(concurrent_factory, app_session) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 10


async def test_parallel_appends_produce_a_single_line(concurrent_factory, app_session) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True
    assert result.events_verified == 10


async def test_parallel_appends_take_distinct_sequence_numbers(
    concurrent_factory,
) -> None:
    numbers = await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    assert len(set(numbers)) == 10


async def test_parallel_appends_produce_distinct_chain_hashes(
    concurrent_factory, app_session
) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    distinct = (
        await app_session.execute(text("SELECT count(DISTINCT chain_hash) FROM audit_events"))
    ).scalar_one()
    assert distinct == 10


async def test_parallel_appends_produce_distinct_prev_hashes(
    concurrent_factory, app_session
) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    distinct = (
        await app_session.execute(text("SELECT count(DISTINCT prev_hash) FROM audit_events"))
    ).scalar_one()
    assert distinct == 10


async def test_exactly_one_event_links_to_genesis(concurrent_factory, app_session) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    count = (
        await app_session.execute(
            text("SELECT count(*) FROM audit_events WHERE prev_hash = :g"),
            {"g": genesis_prev_hash()},
        )
    ).scalar_one()
    assert count == 1


async def test_every_link_points_at_a_real_predecessor(concurrent_factory, app_session) -> None:
    await asyncio.gather(
        *[append_through(concurrent_factory, f"actor-{index}") for index in range(10)]
    )
    orphans = (
        await app_session.execute(
            text(
                "SELECT count(*) FROM audit_events e "
                "WHERE e.prev_hash <> :g "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM audit_events p WHERE p.chain_hash = e.prev_hash"
                ")"
            ),
            {"g": genesis_prev_hash()},
        )
    ).scalar_one()
    assert orphans == 0


async def test_a_parallel_duplicate_event_id_lands_once(concurrent_factory, app_session) -> None:
    event_id = str(uuid.uuid4())

    async def append_same() -> int:
        async with concurrent_factory() as session:
            result = await AuditRepository(session).append(
                event_id=event_id,
                occurred_at=datetime.now(UTC),
                source_service=common_pb2.SOURCE_SERVICE_AUTH,
                actor="duplicate",
                severity=common_pb2.SEVERITY_INFO,
                trace_id="",
                payload_kind=LIFECYCLE_KIND,
                schema_version=1,
                event_bytes=make_payload(actor="duplicate"),
            )
            await session.commit()
            return result.sequence_number

    results = await asyncio.gather(*[append_same() for _ in range(5)], return_exceptions=True)
    landed = [item for item in results if not isinstance(item, Exception)]
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 1
    assert len(set(landed)) == 1


async def test_the_advisory_lock_is_released_after_commit(concurrent_factory, app_session) -> None:
    await append_through(concurrent_factory, "first")
    held = (
        await app_session.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"))
    ).scalar_one()
    assert held == 0


async def test_a_disposed_engine_is_not_reused(database_settings: None) -> None:
    first = database_module.get_engine()
    await database_module.dispose_engine()
    second = database_module.get_engine()
    assert second is not first


async def test_a_disposed_engine_leaves_no_stale_sessionmaker(database_settings: None) -> None:
    database_module.get_sessionmaker()
    await database_module.dispose_engine()
    factory = database_module.get_sessionmaker()
    async with factory() as session:
        value = (await session.execute(text("SELECT 1"))).scalar_one()
    assert value == 1
    await database_module.dispose_engine()


async def test_a_disposed_owner_engine_leaves_no_stale_sessionmaker(
    database_settings: None,
) -> None:
    database_module.get_owner_sessionmaker()
    await database_module.dispose_owner_engine()
    factory = database_module.get_owner_sessionmaker()
    async with factory() as session:
        value = (await session.execute(text("SELECT 1"))).scalar_one()
    assert value == 1
    await database_module.dispose_owner_engine()
