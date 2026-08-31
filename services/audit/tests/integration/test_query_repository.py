from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.repositories.audit_repository import AuditRepository
from app.server.grpc_gen import audit_pb2, common_pb2
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


BASE = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def seed_varied(session) -> None:
    rows = [
        ("actor-a", common_pb2.SOURCE_SERVICE_AUTH, common_pb2.SEVERITY_INFO, 0),
        ("actor-b", common_pb2.SOURCE_SERVICE_AUTH, common_pb2.SEVERITY_WARNING, 1),
        ("actor-a", common_pb2.SOURCE_SERVICE_API, common_pb2.SEVERITY_WARNING, 2),
        ("actor-c", common_pb2.SOURCE_SERVICE_API, common_pb2.SEVERITY_INFO, 3),
        ("actor-b", common_pb2.SOURCE_SERVICE_AI, common_pb2.SEVERITY_CRITICAL, 4),
        ("actor-a", common_pb2.SOURCE_SERVICE_AUTH, common_pb2.SEVERITY_NOTICE, 5),
    ]
    for actor, service, severity, offset in rows:
        await append_one(
            session,
            actor=actor,
            source_service=service,
            severity=severity,
            occurred_at=BASE + timedelta(days=offset),
        )


async def query(session, **overrides):
    defaults = {
        "from_time": None,
        "to_time": None,
        "source_service": 0,
        "actor": "",
        "min_severity": 0,
        "page_size": 100,
        "after_sequence_number": None,
    }
    defaults.update(overrides)
    return await AuditRepository(session).query(**defaults)


async def test_an_unfiltered_query_returns_every_row(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session)
    assert len(rows) == 6


async def test_rows_come_back_in_sequence_order(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session)
    numbers = [row.sequence_number for row in rows]
    assert numbers == sorted(numbers)


async def test_an_empty_log_returns_nothing(app_session) -> None:
    assert await query(app_session) == []


async def test_the_actor_filter_is_exact(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, actor="actor-a")
    assert len(rows) == 3
    assert {row.actor for row in rows} == {"actor-a"}


async def test_the_actor_filter_does_not_match_a_prefix(app_session) -> None:
    await seed_varied(app_session)
    assert await query(app_session, actor="actor") == []


async def test_an_unknown_actor_returns_nothing(app_session) -> None:
    await seed_varied(app_session)
    assert await query(app_session, actor="nobody") == []


async def test_the_source_service_filter_selects_one_service(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, source_service=common_pb2.SOURCE_SERVICE_AUTH)
    assert len(rows) == 3
    assert {row.source_service for row in rows} == {common_pb2.SOURCE_SERVICE_AUTH}


async def test_the_severity_filter_is_a_floor(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, min_severity=common_pb2.SEVERITY_WARNING)
    assert all(row.severity >= common_pb2.SEVERITY_WARNING for row in rows)
    assert len(rows) == 3


async def test_the_highest_severity_filter_selects_only_critical(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, min_severity=common_pb2.SEVERITY_CRITICAL)
    assert len(rows) == 1
    assert rows[0].actor == "actor-b"


async def test_the_lower_time_bound_is_inclusive(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, from_time=BASE)
    assert len(rows) == 6


async def test_the_upper_time_bound_is_exclusive(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, to_time=BASE + timedelta(days=5))
    assert len(rows) == 5


async def test_a_time_window_selects_the_middle(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(
        app_session,
        from_time=BASE + timedelta(days=2),
        to_time=BASE + timedelta(days=4),
    )
    assert len(rows) == 2


async def test_a_window_before_everything_returns_nothing(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, to_time=BASE - timedelta(days=1))
    assert rows == []


async def test_filters_combine(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(
        app_session,
        actor="actor-a",
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
    )
    assert len(rows) == 2


async def test_combined_filters_can_exclude_everything(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(
        app_session,
        actor="actor-c",
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
    )
    assert rows == []


async def test_a_page_size_limits_the_result(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, page_size=2)
    assert len(rows) == 2


async def test_the_next_page_resumes_after_the_last_row(app_session) -> None:
    await seed_varied(app_session)
    first = await query(app_session, page_size=2)
    second = await query(app_session, page_size=2, after_sequence_number=first[-1].sequence_number)
    assert [row.sequence_number for row in second] == [3, 4]


async def test_paging_covers_every_row_exactly_once(app_session) -> None:
    await seed_varied(app_session)
    seen: list[int] = []
    cursor = None
    while True:
        page = await query(app_session, page_size=2, after_sequence_number=cursor)
        if not page:
            break
        seen.extend(row.sequence_number for row in page)
        cursor = page[-1].sequence_number
    assert seen == [1, 2, 3, 4, 5, 6]


async def test_paging_respects_the_filters(app_session) -> None:
    await seed_varied(app_session)
    seen: list[str] = []
    cursor = None
    while True:
        page = await query(app_session, actor="actor-a", page_size=1, after_sequence_number=cursor)
        if not page:
            break
        seen.extend(row.actor for row in page)
        cursor = page[-1].sequence_number
    assert seen == ["actor-a", "actor-a", "actor-a"]


async def test_a_cursor_past_the_end_returns_nothing(app_session) -> None:
    await seed_varied(app_session)
    assert await query(app_session, after_sequence_number=999) == []


async def test_an_erased_row_is_still_returned(app_session, owner_session) -> None:
    await seed_varied(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text(
            "UPDATE audit_events SET event_bytes = NULL, erased_at = now(), "
            "erasure_reason = 1 WHERE sequence_number = 3"
        )
    )
    await owner_session.commit()
    rows = await query(app_session)
    erased = [row for row in rows if row.erased_at is not None]
    assert len(rows) == 6
    assert len(erased) == 1
    assert erased[0].event_bytes is None


async def test_the_stored_payload_round_trips(app_session) -> None:
    await seed_varied(app_session)
    rows = await query(app_session, page_size=1)
    parsed = audit_pb2.AuditEvent()
    parsed.ParseFromString(rows[0].event_bytes)
    assert parsed.actor == "actor-a"


async def test_count_since_counts_the_tail(app_session) -> None:
    await seed_varied(app_session)
    assert await AuditRepository(app_session).count_since(4) == 2


async def test_count_since_zero_counts_everything(app_session) -> None:
    await seed_varied(app_session)
    assert await AuditRepository(app_session).count_since(0) == 6


async def test_event_at_reads_one_row(app_session) -> None:
    await seed_varied(app_session)
    row = await AuditRepository(app_session).event_at(2)
    assert row is not None
    assert row.actor == "actor-b"


async def test_event_at_an_absent_sequence_returns_nothing(app_session) -> None:
    await seed_varied(app_session)
    assert await AuditRepository(app_session).event_at(99) is None
