from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.chain import compute_chain_hash, compute_leaf_hash, genesis_prev_hash
from app.repositories.audit_repository import AuditRepository
from app.server.grpc_gen import audit_pb2, common_pb2

pytestmark = pytest.mark.integration


LIFECYCLE_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number


def make_payload(actor: str = "actor-1", version: str = "0.1.0") -> bytes:
    event = audit_pb2.AuditEvent(
        schema_version=1,
        event_id=str(uuid.uuid4()),
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
        actor=actor,
        severity=common_pb2.SEVERITY_INFO,
    )
    event.occurred_at.FromDatetime(datetime.now(UTC))
    event.service_lifecycle.version = version
    return event.SerializeToString(deterministic=True)


async def append_one(session, actor: str = "actor-1", event_id: str | None = None, **overrides):
    events = AuditRepository(session)
    payload = overrides.pop("event_bytes", None) or make_payload(actor)
    defaults = {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC),
        "source_service": common_pb2.SOURCE_SERVICE_AUTH,
        "actor": actor,
        "severity": common_pb2.SEVERITY_INFO,
        "trace_id": "",
        "payload_kind": LIFECYCLE_KIND,
        "schema_version": 1,
        "event_bytes": payload,
    }
    defaults.update(overrides)
    result = await events.append(**defaults)
    await session.commit()
    return result


async def test_the_first_event_links_to_genesis(app_session) -> None:
    result = await append_one(app_session)
    row = (
        await app_session.execute(
            text("SELECT prev_hash FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    ).scalar_one()
    assert bytes(row) == genesis_prev_hash()


async def test_the_first_event_takes_sequence_number_one(app_session) -> None:
    result = await append_one(app_session)
    assert result.sequence_number == 1


async def test_sequence_numbers_increase(app_session) -> None:
    first = await append_one(app_session)
    second = await append_one(app_session)
    assert second.sequence_number > first.sequence_number


async def test_each_event_links_to_its_predecessor(app_session) -> None:
    first = await append_one(app_session)
    second = await append_one(app_session)
    row = (
        await app_session.execute(
            text("SELECT prev_hash FROM audit_events WHERE sequence_number = :s"),
            {"s": second.sequence_number},
        )
    ).scalar_one()
    assert bytes(row) == first.chain_hash


async def test_the_stored_leaf_hash_matches_the_payload(app_session) -> None:
    payload = make_payload()
    result = await append_one(app_session, event_bytes=payload)
    assert result.leaf_hash == compute_leaf_hash(payload)


async def test_the_stored_chain_hash_matches_the_linkage(app_session) -> None:
    first = await append_one(app_session)
    payload = make_payload(actor="actor-2")
    second = await append_one(app_session, actor="actor-2", event_bytes=payload)
    expected = compute_chain_hash(first.chain_hash, compute_leaf_hash(payload))
    assert second.chain_hash == expected


async def test_the_payload_is_stored_verbatim(app_session) -> None:
    payload = make_payload()
    result = await append_one(app_session, event_bytes=payload)
    stored = (
        await app_session.execute(
            text("SELECT event_bytes FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    ).scalar_one()
    assert bytes(stored) == payload


async def test_a_repeated_event_id_returns_the_original_position(app_session) -> None:
    event_id = str(uuid.uuid4())
    first = await append_one(app_session, event_id=event_id)
    second = await append_one(app_session, event_id=event_id)
    assert second.sequence_number == first.sequence_number
    assert second.duplicate is True


async def test_a_repeated_event_id_does_not_extend_the_chain(app_session) -> None:
    event_id = str(uuid.uuid4())
    await append_one(app_session, event_id=event_id)
    await append_one(app_session, event_id=event_id)
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 1


async def test_a_repeated_event_id_returns_the_original_hashes(app_session) -> None:
    event_id = str(uuid.uuid4())
    first = await append_one(app_session, event_id=event_id)
    second = await append_one(app_session, event_id=event_id)
    assert second.chain_hash == first.chain_hash
    assert second.leaf_hash == first.leaf_hash


async def test_two_events_cannot_share_a_predecessor(app_session, owner_session) -> None:
    first = await append_one(app_session)
    payload = make_payload(actor="forged")
    leaf = compute_leaf_hash(payload)
    with pytest.raises(IntegrityError):
        await owner_session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, 1, now(), 2, 'forged', 1, '', :kind, 1,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash
                )
                """
            ),
            {
                "event_id": str(uuid.uuid4()),
                "kind": LIFECYCLE_KIND,
                "event_bytes": payload,
                "leaf_hash": leaf,
                "prev_hash": genesis_prev_hash(),
                "chain_hash": compute_chain_hash(genesis_prev_hash(), leaf),
            },
        )
    await owner_session.rollback()
    assert first.sequence_number == 1


async def test_two_events_cannot_share_a_chain_hash(app_session, owner_session) -> None:
    first = await append_one(app_session)
    with pytest.raises(IntegrityError):
        await owner_session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, 1, now(), 2, 'forged', 1, '', :kind, 1,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash
                )
                """
            ),
            {
                "event_id": str(uuid.uuid4()),
                "kind": LIFECYCLE_KIND,
                "event_bytes": make_payload(actor="forged"),
                "leaf_hash": bytes(range(32)),
                "prev_hash": first.chain_hash,
                "chain_hash": first.chain_hash,
            },
        )
    await owner_session.rollback()


async def test_a_short_hash_is_refused_by_the_schema(owner_session) -> None:
    with pytest.raises(IntegrityError):
        await owner_session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, 1, now(), 2, 'a', 1, '', :kind, 1,
                    :event_bytes, :short, :prev_hash, :chain_hash
                )
                """
            ),
            {
                "event_id": str(uuid.uuid4()),
                "kind": LIFECYCLE_KIND,
                "event_bytes": make_payload(),
                "short": bytes(16),
                "prev_hash": genesis_prev_hash(),
                "chain_hash": bytes(range(32)),
            },
        )
    await owner_session.rollback()


async def test_a_zero_schema_version_is_refused_by_the_schema(owner_session) -> None:
    with pytest.raises(IntegrityError):
        await owner_session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, 0, now(), 2, 'a', 1, '', :kind, 1,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash
                )
                """
            ),
            {
                "event_id": str(uuid.uuid4()),
                "kind": LIFECYCLE_KIND,
                "event_bytes": make_payload(),
                "leaf_hash": bytes(range(32)),
                "prev_hash": genesis_prev_hash(),
                "chain_hash": bytes(range(32, 64)),
            },
        )
    await owner_session.rollback()


async def test_an_erased_row_with_a_payload_is_refused_by_the_schema(owner_session) -> None:
    with pytest.raises(IntegrityError):
        await owner_session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash,
                    erased_at, erasure_reason
                ) VALUES (
                    :event_id, 1, now(), 2, 'a', 1, '', :kind, 1,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash,
                    now(), 1
                )
                """
            ),
            {
                "event_id": str(uuid.uuid4()),
                "kind": LIFECYCLE_KIND,
                "event_bytes": make_payload(),
                "leaf_hash": bytes(range(32)),
                "prev_hash": genesis_prev_hash(),
                "chain_hash": bytes(range(32, 64)),
            },
        )
    await owner_session.rollback()


async def test_a_chain_of_events_verifies(app_session) -> None:
    for index in range(8):
        await append_one(app_session, actor=f"actor-{index}")
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True
    assert result.events_verified == 8


async def test_verification_walks_a_bounded_range(app_session) -> None:
    for index in range(8):
        await append_one(app_session, actor=f"actor-{index}")
    result = await AuditRepository(app_session).verify(3, 6)
    assert result.chain_intact is True
    assert result.events_verified == 4


async def test_the_tail_state_reports_the_last_event(app_session) -> None:
    await append_one(app_session)
    last = await append_one(app_session)
    tail = await AuditRepository(app_session).tail_state()
    assert tail.prev_hash == last.chain_hash
    assert tail.tail_sequence_number == last.sequence_number
    assert tail.tree_size == 2


async def test_the_tail_state_of_an_empty_log_is_genesis(app_session) -> None:
    tail = await AuditRepository(app_session).tail_state()
    assert tail.prev_hash == genesis_prev_hash()
    assert tail.tree_size == 0
    assert tail.tail_sequence_number == 0


async def test_the_count_matches_the_rows(app_session) -> None:
    for _ in range(5):
        await append_one(app_session)
    assert await AuditRepository(app_session).count() == 5


async def test_backdated_events_keep_insertion_order(app_session) -> None:
    old = datetime.now(UTC) - timedelta(days=3)
    first = await append_one(app_session, occurred_at=datetime.now(UTC))
    second = await append_one(app_session, occurred_at=old)
    assert second.sequence_number > first.sequence_number
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True
