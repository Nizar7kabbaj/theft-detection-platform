from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.chain import (
    GENESIS_CHECKPOINT_HASH,
    GENESIS_PREV_HASH,
    compute_chain_hash,
    compute_leaf_hash,
)
from app.core.config import get_settings
from app.core.signing import build_checkpoint_payload, get_signer
from app.repositories.audit_repository import (
    VERIFY_FAILURE_LEAF_MISMATCH,
    VERIFY_FAILURE_NONE,
    AuditRepository,
)
from app.server.grpc_gen import audit_pb2, common_pb2
from app.services.checkpoint_service import verify_checkpoints
from app.services.retention import RetentionService
from tools.operator import erase_subject

logger = logging.getLogger("harness")

LIFECYCLE_PAYLOAD_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number
ERASURE_PAYLOAD_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["data_subject_erasure"].number


@dataclass(slots=True)
class Proof:
    name: str
    expected: str
    observed: str

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


def _harness_url() -> str:
    password = os.environ["HARNESS_POSTGRES_PASSWORD"]
    host = os.environ.get("HARNESS_POSTGRES_HOST", "postgres-harness")
    return f"postgresql+asyncpg://audit_owner:{password}@{host}:5432/auditdb"


def _payload(index: int, actor: str) -> bytes:
    event = audit_pb2.AuditEvent(
        schema_version=get_settings().schema_version,
        event_id=str(uuid.uuid4()),
        source_service=common_pb2.SOURCE_SERVICE_AUDIT,
        trace_id=f"{index:032x}",
        actor=actor,
        severity=common_pb2.SEVERITY_INFO,
    )
    event.occurred_at.FromDatetime(datetime.now(UTC))
    event.service_lifecycle.service = common_pb2.SOURCE_SERVICE_AUDIT
    event.service_lifecycle.event_kind = audit_pb2.LIFECYCLE_EVENT_KIND_STARTED
    event.service_lifecycle.version = "0.1.0"
    return event.SerializeToString()


async def _insert(session: AsyncSession, index: int, persisted_at: datetime) -> None:
    events = AuditRepository(session)
    payload = _payload(index, f"actor-{index % 4}")
    tail = await events.tail_state()
    leaf = compute_leaf_hash(payload)
    chain = compute_chain_hash(tail.prev_hash, leaf)
    await session.execute(
        text(
            """
            INSERT INTO audit_events (
                event_id, schema_version, occurred_at, persisted_at,
                source_service, actor, severity, trace_id, payload_kind,
                hash_algorithm, event_bytes, leaf_hash, prev_hash, chain_hash
            ) VALUES (
                :event_id, 1, :occurred_at, :persisted_at,
                0, :actor, 1, :trace_id, :payload_kind,
                1, :event_bytes, :leaf_hash, :prev_hash, :chain_hash
            )
            """
        ),
        {
            "event_id": str(uuid.uuid4()),
            "occurred_at": persisted_at,
            "persisted_at": persisted_at,
            "actor": f"actor-{index % 4}",
            "trace_id": f"{index:032x}",
            "payload_kind": LIFECYCLE_PAYLOAD_KIND,
            "event_bytes": payload,
            "leaf_hash": leaf,
            "prev_hash": tail.prev_hash,
            "chain_hash": chain,
        },
    )


async def _seed(factory, count: int, oldest_age_days: int) -> None:
    base = datetime.now(UTC) - timedelta(days=oldest_age_days)
    async with factory() as session:
        for index in range(count):
            await _insert(session, index, base + timedelta(days=index))
        await session.commit()
    logger.info("seeded %d events spanning %d days", count, count)


async def _reset(factory) -> None:
    async with factory() as session:
        await session.execute(text("SET LOCAL audit.maintenance = 'on'"))
        await session.execute(text("DELETE FROM audit_events"))
        await session.execute(text("DELETE FROM audit_chain_segments"))
        await session.execute(text("TRUNCATE audit_checkpoints RESTART IDENTITY"))
        await session.execute(
            text("ALTER TABLE audit_events ALTER COLUMN sequence_number RESTART WITH 1")
        )
        await session.execute(
            text("ALTER TABLE audit_chain_segments ALTER COLUMN segment_id RESTART WITH 1")
        )
        await session.commit()


async def _proof_corrupted_row_fails(factory) -> Proof:
    target = 3
    async with factory() as session:
        original = (
            await session.execute(
                text("SELECT event_bytes FROM audit_events WHERE sequence_number = :s"),
                {"s": target},
            )
        ).scalar_one()
        await session.execute(text("SET LOCAL audit.maintenance = 'on'"))
        await session.execute(
            text("UPDATE audit_events SET event_bytes = :b WHERE sequence_number = :s"),
            {"b": original + b"\x00tampered", "s": target},
        )
        result = await AuditRepository(session).verify(None, None)
        await session.rollback()

    return Proof(
        "corrupted row fails verification at the right sequence",
        f"intact False break {target} kind {VERIFY_FAILURE_LEAF_MISMATCH}",
        f"intact {result.chain_intact} break {result.break_at_sequence_number} "
        f"kind {result.failure_kind}",
    )


async def _proof_erased_row_passes(factory) -> Proof:
    target = 5
    async with factory() as session:
        await session.execute(text("SET LOCAL audit.maintenance = 'on'"))
        await session.execute(
            text(
                "UPDATE audit_events SET event_bytes = NULL, "
                "erased_at = now(), erasure_reason = 1 "
                "WHERE sequence_number = :s"
            ),
            {"s": target},
        )
        result = await AuditRepository(session).verify(None, None)
        await session.rollback()

    return Proof(
        "tombstoned row passes verification",
        "intact True erased 1",
        f"intact {result.chain_intact} erased {result.erased_rows_verified}",
    )


async def _proof_operator_erasure_audited(factory) -> Proof:
    async with factory() as session:
        before = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_events "
                    "WHERE actor = 'actor-1' AND erased_at IS NULL"
                )
            )
        ).scalar_one()

    code = await erase_subject("actor-1", "harness", False)

    async with factory() as session:
        erased = (
            await session.execute(
                text("SELECT count(*) FROM audit_events WHERE erased_at IS NOT NULL")
            )
        ).scalar_one()
        recorded = (
            await session.execute(
                text("SELECT count(*) FROM audit_events WHERE payload_kind = :kind"),
                {"kind": ERASURE_PAYLOAD_KIND},
            )
        ).scalar_one()
        result = await AuditRepository(session).verify(None, None)

    return Proof(
        "erasure tombstones rows and records itself in the chain",
        f"exit 0 erased {before} recorded 1 intact True",
        f"exit {code} erased {erased} recorded {recorded} intact {result.chain_intact}",
    )


async def _proof_full_rewrite_caught(factory) -> Proof:
    async with factory() as session:
        events = AuditRepository(session)
        tail = await events.tail_state()
        signer = get_signer()
        payload = build_checkpoint_payload(
            key_id=signer.key_id,
            tree_size=tail.tree_size,
            tail_sequence_number=tail.tail_sequence_number,
            tail_chain_hash=tail.prev_hash,
            prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
            signature_algorithm=signer.signature_algorithm,
        )
        await events.append_checkpoint(
            tail_sequence_number=tail.tail_sequence_number,
            tail_chain_hash=tail.prev_hash,
            tree_size=tail.tree_size,
            signature=signer.sign(payload),
            key_id=signer.key_id,
            prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
            payload=payload,
            signature_algorithm=signer.signature_algorithm,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))

        rows = (
            await session.execute(
                text(
                    "SELECT sequence_number, event_bytes, leaf_hash, erased_at "
                    "FROM audit_events ORDER BY sequence_number ASC"
                )
            )
        ).all()

        target = next(row[0] for row in rows if row[3] is None)
        prev = GENESIS_PREV_HASH
        for sequence_number, event_bytes, existing_leaf, erased_at in rows:
            if erased_at is not None:
                leaf = existing_leaf
                chain = compute_chain_hash(prev, leaf)
                await session.execute(
                    text(
                        "UPDATE audit_events SET prev_hash = :p, chain_hash = :c "
                        "WHERE sequence_number = :s"
                    ),
                    {"p": prev, "c": chain, "s": sequence_number},
                )
            else:
                payload_bytes = (
                    event_bytes + b"\x00forged" if (sequence_number == target) else event_bytes
                )
                leaf = compute_leaf_hash(payload_bytes)
                chain = compute_chain_hash(prev, leaf)
                await session.execute(
                    text(
                        "UPDATE audit_events SET event_bytes = :b, leaf_hash = :l, "
                        "prev_hash = :p, chain_hash = :c WHERE sequence_number = :s"
                    ),
                    {
                        "b": payload_bytes,
                        "l": leaf,
                        "p": prev,
                        "c": chain,
                        "s": sequence_number,
                    },
                )
            prev = chain

        chain_result = await AuditRepository(session).verify(None, None)
        checkpoint_result = await verify_checkpoints(AuditRepository(session))
        await session.rollback()

    caught = checkpoint_result.failure_kind != VERIFY_FAILURE_NONE
    return Proof(
        "checkpoint catches a fully recomputed history",
        "chain intact True checkpoint caught True",
        f"chain intact {chain_result.chain_intact} checkpoint caught {caught}",
    )


async def _proof_seal_preserves_chain(factory) -> Proof:
    async with factory() as session:
        service = RetentionService(session)
        candidate = await service.next_segment()
        if candidate is None:
            await session.rollback()
            return Proof(
                "sealing drops rows and preserves linkage",
                "segment sealed",
                "nothing eligible",
            )
        outcome = await service.seal_and_drop(candidate)
        await session.commit()

    async with factory() as session:
        result = await AuditRepository(session).verify(None, None)

    return Proof(
        "sealing drops rows and preserves linkage",
        f"dropped {outcome.row_count} intact True",
        f"dropped {outcome.row_count} intact {result.chain_intact}",
    )


async def _run(keep: bool) -> int:
    engine = create_async_engine(_harness_url(), pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    proofs: list[Proof] = []
    try:
        await _reset(factory)
        await _seed(factory, 40, 400)
        proofs.append(await _proof_corrupted_row_fails(factory))
        proofs.append(await _proof_erased_row_passes(factory))
        proofs.append(await _proof_operator_erasure_audited(factory))
        proofs.append(await _proof_full_rewrite_caught(factory))
        proofs.append(await _proof_seal_preserves_chain(factory))
        if not keep:
            await _reset(factory)
    finally:
        await engine.dispose()

    width = max(len(p.name) for p in proofs)
    for proof in proofs:
        status = "pass" if proof.passed else "fail"
        print(f"{proof.name.ljust(width)}  {status}")
        if not proof.passed:
            print(f"{' ' * width}  expected {proof.expected}")
            print(f"{' ' * width}  observed {proof.observed}")

    failed = [p for p in proofs if not p.passed]
    print(f"\n{len(proofs) - len(failed)} of {len(proofs)} proofs passed")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="audit-harness")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level="INFO", format="%(message)s", stream=sys.stderr)
    sys.exit(asyncio.run(_run(args.keep)))


if __name__ == "__main__":
    main()
