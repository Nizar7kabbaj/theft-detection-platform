from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.core import pseudonym
from app.core.chain import compute_chain_hash, compute_leaf_hash
from app.core.config import get_settings
from app.core.database import dispose_owner_engine, get_owner_sessionmaker
from app.db.models.audit_event import AuditEvent
from app.repositories.audit_repository import AuditRepository
from app.server.grpc_gen import audit_pb2, common_pb2
from app.services.retention import RetentionError, RetentionService, retention_cutoff

logger = logging.getLogger("audit.operator")

ACTOR_DOMAIN = "actor"


async def _seal(dry_run: bool, max_segments: int) -> int:
    factory = get_owner_sessionmaker()
    sealed = 0
    for _ in range(max_segments):
        async with factory() as session:
            service = RetentionService(session)
            try:
                candidate = await service.next_segment()
            except RetentionError as exc:
                logger.error("%s", exc)
                await session.rollback()
                return 1
            if candidate is None:
                break
            if dry_run:
                logger.info(
                    "would seal sequences %d to %d, %d rows, persisted %s to %s",
                    candidate.first_sequence_number,
                    candidate.last_sequence_number,
                    candidate.row_count,
                    candidate.covers_from.isoformat(),
                    candidate.covers_to.isoformat(),
                )
                await session.rollback()
                sealed += 1
                break
            try:
                outcome = await service.seal_and_drop(candidate)
            except RetentionError as exc:
                logger.error("%s", exc)
                await session.rollback()
                return 1
            await session.commit()
            sealed += 1
            logger.info(
                "segment %d committed, terminal hash %s",
                outcome.segment_id,
                outcome.terminal_chain_hash.hex(),
            )
    if sealed == 0:
        logger.info("nothing eligible, cutoff %s", retention_cutoff().isoformat())
    return 0


async def erase_subject(subject: str, requested_by: str, dry_run: bool) -> int:
    settings = get_settings()
    factory = get_owner_sessionmaker()
    subject_hmac = pseudonym.pseudonymize(ACTOR_DOMAIN, subject)

    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditEvent.sequence_number)
                    .where(AuditEvent.actor == subject)
                    .where(AuditEvent.erased_at.is_(None))
                    .order_by(AuditEvent.sequence_number.asc())
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            logger.info("no live rows for subject")
            return 0

        if dry_run:
            logger.info(
                "would erase %d rows, sequences %d to %d",
                len(rows),
                rows[0],
                rows[-1],
            )
            return 0

        events = AuditRepository(session)
        await events.lock_chain()

        event = audit_pb2.AuditEvent(
            schema_version=settings.schema_version,
            event_id=str(uuid.uuid4()),
            source_service=common_pb2.SOURCE_SERVICE_AUDIT,
            trace_id="0" * 32,
            actor=pseudonym.pseudonymize(ACTOR_DOMAIN, requested_by).hex()[:64],
            severity=common_pb2.SEVERITY_NOTICE,
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        event.data_subject_erasure.data_subject_hmac = subject_hmac
        event.data_subject_erasure.requested_by = requested_by
        event.data_subject_erasure.scopes.append(audit_pb2.ERASURE_SCOPE_AUDIT_PAYLOADS)
        event.data_subject_erasure.records_erased = len(rows)
        event.data_subject_erasure.completed = True

        payload = event.SerializeToString()
        tail = await events.tail_state()
        leaf = compute_leaf_hash(payload)
        chain = compute_chain_hash(tail.prev_hash, leaf)

        await session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, :schema_version, :occurred_at, :source_service, :actor,
                    :severity, :trace_id, :payload_kind, 1,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash
                )
                """
            ),
            {
                "event_id": event.event_id,
                "schema_version": event.schema_version,
                "occurred_at": event.occurred_at.ToDatetime(tzinfo=UTC),
                "source_service": event.source_service,
                "actor": event.actor,
                "severity": event.severity,
                "trace_id": event.trace_id,
                "payload_kind": audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name[
                    "data_subject_erasure"
                ].number,
                "event_bytes": payload,
                "leaf_hash": leaf,
                "prev_hash": tail.prev_hash,
                "chain_hash": chain,
            },
        )

        await session.execute(text("SET LOCAL audit.maintenance = 'on'"))
        result = await session.execute(
            text(
                "UPDATE audit_events SET event_bytes = NULL, erased_at = now(), "
                "erasure_reason = 1 WHERE actor = :actor AND erased_at IS NULL "
                "AND event_bytes IS NOT NULL"
            ),
            {"actor": subject},
        )

        check = await AuditRepository(session).verify(None, None)
        if not check.chain_intact:
            logger.error(
                "verification failed after erasure at sequence %s kind %d",
                check.break_at_sequence_number,
                check.failure_kind,
            )
            await session.rollback()
            return 1

        await session.commit()
        logger.info(
            "erased %d rows, erasure event at chain hash %s",
            result.rowcount,
            chain.hex(),
        )
    return 0


async def _verify() -> int:
    factory = get_owner_sessionmaker()
    async with factory() as session:
        result = await AuditRepository(session).verify(None, None)
    logger.info(
        "chain_intact=%s failure_kind=%d break_at=%s events=%d erased=%d checkpoints=%d",
        result.chain_intact,
        result.failure_kind,
        result.break_at_sequence_number,
        result.events_verified,
        result.erased_rows_verified,
        result.checkpoints_verified,
    )
    return 0 if result.chain_intact else 2


async def _status() -> int:
    settings = get_settings()
    factory = get_owner_sessionmaker()
    async with factory() as session:
        tail = await AuditRepository(session).tail_state()
    logger.info(
        "rows=%d tail_sequence=%d retention_days=%d segment_days=%d cutoff=%s",
        tail.tree_size,
        tail.tail_sequence_number,
        settings.retention_days,
        settings.segment_interval_days,
        retention_cutoff().isoformat(),
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audit-operator")
    sub = parser.add_subparsers(dest="command", required=True)

    seal = sub.add_parser("seal")
    seal.add_argument("--dry-run", action="store_true")
    seal.add_argument("--max-segments", type=int, default=1)

    erase = sub.add_parser("erase")
    erase.add_argument("--subject", required=True)
    erase.add_argument("--requested-by", required=True)
    erase.add_argument("--dry-run", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("status")

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    try:
        if args.command == "seal":
            return await _seal(args.dry_run, args.max_segments)
        if args.command == "erase":
            return await erase_subject(args.subject, args.requested_by, args.dry_run)
        if args.command == "verify":
            return await _verify()
        return await _status()
    finally:
        await dispose_owner_engine()


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(message)s",
        stream=sys.stderr,
    )
    sys.exit(asyncio.run(_dispatch(args)))


if __name__ == "__main__":
    main()
