from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chain import (
    DEFAULT_HASH_ALGORITHM,
    GENESIS_CHECKPOINT_HASH,
    chain_matches,
    compute_chain_hash,
    compute_checkpoint_hash,
    compute_leaf_hash,
    genesis_prev_hash,
    is_supported,
    leaf_matches,
)
from app.db.models.audit_event import AuditChainSegment, AuditCheckpoint, AuditEvent

logger = logging.getLogger(__name__)

_CHAIN_LOCK_KEY = 8410723461907712001

VERIFY_FAILURE_NONE = 1
VERIFY_FAILURE_LINKAGE_MISMATCH = 2
VERIFY_FAILURE_LEAF_MISMATCH = 3
VERIFY_FAILURE_CHAIN_MISMATCH = 4
VERIFY_FAILURE_MISSING_PAYLOAD = 5
VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID = 6
VERIFY_FAILURE_CHECKPOINT_DIVERGENCE = 7
VERIFY_FAILURE_ALGORITHM_UNSUPPORTED = 8


@dataclass(frozen=True, slots=True)
class AppendResult:
    sequence_number: int
    leaf_hash: bytes
    chain_hash: bytes
    persisted_at: datetime
    duplicate: bool


@dataclass(frozen=True, slots=True)
class VerifyResult:
    chain_intact: bool
    break_at_sequence_number: int | None
    failure_kind: int
    events_verified: int
    erased_rows_verified: int
    checkpoints_verified: int


@dataclass(frozen=True, slots=True)
class TailState:
    prev_hash: bytes
    tree_size: int
    tail_sequence_number: int


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_chain(self) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CHAIN_LOCK_KEY}
        )

    async def _find_by_event_id(self, event_id: str) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent).where(AuditEvent.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def _last_segment(self) -> AuditChainSegment | None:
        result = await self._session.execute(
            select(AuditChainSegment)
            .order_by(AuditChainSegment.last_sequence_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _predecessor(self, sequence_number: int) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.sequence_number < sequence_number)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def tail_state(self) -> TailState:
        result = await self._session.execute(
            select(AuditEvent.chain_hash, AuditEvent.sequence_number)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        row = result.first()
        rows_total = await self.count()
        if row is not None:
            return TailState(row[0], rows_total, row[1])
        segment = await self._last_segment()
        if segment is not None:
            return TailState(
                segment.terminal_chain_hash,
                rows_total,
                segment.last_sequence_number,
            )
        return TailState(genesis_prev_hash(), 0, 0)

    async def append(
        self,
        event_id: str,
        occurred_at: datetime,
        source_service: int,
        actor: str,
        severity: int,
        trace_id: str,
        payload_kind: int,
        schema_version: int,
        event_bytes: bytes,
        hash_algorithm: int = DEFAULT_HASH_ALGORITHM,
    ) -> AppendResult:
        existing = await self._find_by_event_id(event_id)
        if existing is not None:
            return AppendResult(
                existing.sequence_number,
                existing.leaf_hash,
                existing.chain_hash,
                existing.persisted_at,
                True,
            )

        await self.lock_chain()

        existing = await self._find_by_event_id(event_id)
        if existing is not None:
            return AppendResult(
                existing.sequence_number,
                existing.leaf_hash,
                existing.chain_hash,
                existing.persisted_at,
                True,
            )

        tail = await self.tail_state()
        leaf_hash = compute_leaf_hash(event_bytes, hash_algorithm)
        chain_hash = compute_chain_hash(tail.prev_hash, leaf_hash, hash_algorithm)

        result = await self._session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, schema_version, occurred_at, source_service, actor,
                    severity, trace_id, payload_kind, hash_algorithm,
                    event_bytes, leaf_hash, prev_hash, chain_hash
                ) VALUES (
                    :event_id, :schema_version, :occurred_at, :source_service, :actor,
                    :severity, :trace_id, :payload_kind, :hash_algorithm,
                    :event_bytes, :leaf_hash, :prev_hash, :chain_hash
                )
                RETURNING sequence_number, persisted_at
                """
            ),
            {
                "event_id": event_id,
                "schema_version": schema_version,
                "occurred_at": occurred_at,
                "source_service": source_service,
                "actor": actor,
                "severity": severity,
                "trace_id": trace_id,
                "payload_kind": payload_kind,
                "hash_algorithm": hash_algorithm,
                "event_bytes": event_bytes,
                "leaf_hash": leaf_hash,
                "prev_hash": tail.prev_hash,
                "chain_hash": chain_hash,
            },
        )
        row = result.one()
        return AppendResult(row[0], leaf_hash, chain_hash, row[1], False)

    def _apply_filters(
        self,
        stmt: Select[tuple[AuditEvent]],
        from_time: datetime | None,
        to_time: datetime | None,
        source_service: int,
        actor: str,
        min_severity: int,
    ) -> Select[tuple[AuditEvent]]:
        if from_time is not None:
            stmt = stmt.where(AuditEvent.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(AuditEvent.occurred_at < to_time)
        if source_service > 0:
            stmt = stmt.where(AuditEvent.source_service == source_service)
        if actor:
            stmt = stmt.where(AuditEvent.actor == actor)
        if min_severity > 0:
            stmt = stmt.where(AuditEvent.severity >= min_severity)
        return stmt

    async def query(
        self,
        from_time: datetime | None,
        to_time: datetime | None,
        source_service: int,
        actor: str,
        min_severity: int,
        page_size: int,
        after_sequence_number: int | None,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent)
        stmt = self._apply_filters(stmt, from_time, to_time, source_service, actor, min_severity)
        if after_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number > after_sequence_number)
        stmt = stmt.order_by(AuditEvent.sequence_number.asc()).limit(page_size)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _seed_expected_prev(self, from_sequence_number: int | None) -> bytes:
        if from_sequence_number is None:
            segment = await self._last_segment()
            first = await self._session.execute(
                select(AuditEvent.prev_hash).order_by(AuditEvent.sequence_number.asc()).limit(1)
            )
            head = first.scalar_one_or_none()
            if head is None:
                return genesis_prev_hash()
            if segment is not None and segment.terminal_chain_hash == head:
                return segment.terminal_chain_hash
            return genesis_prev_hash()

        predecessor = await self._predecessor(from_sequence_number)
        if predecessor is not None:
            return predecessor.chain_hash
        segment = await self._last_segment()
        if segment is not None:
            return segment.terminal_chain_hash
        return genesis_prev_hash()

    async def verify(
        self,
        from_sequence_number: int | None,
        to_sequence_number: int | None,
    ) -> VerifyResult:
        stmt = select(AuditEvent).order_by(AuditEvent.sequence_number.asc())
        if from_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number >= from_sequence_number)
        if to_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number <= to_sequence_number)

        expected_prev = await self._seed_expected_prev(from_sequence_number)
        verified = 0
        erased_verified = 0

        stream = await self._session.stream_scalars(stmt)
        async for row in stream:
            if not is_supported(row.hash_algorithm):
                return VerifyResult(
                    False,
                    row.sequence_number,
                    VERIFY_FAILURE_ALGORITHM_UNSUPPORTED,
                    verified,
                    erased_verified,
                    0,
                )

            if row.prev_hash != expected_prev:
                return VerifyResult(
                    False,
                    row.sequence_number,
                    VERIFY_FAILURE_LINKAGE_MISMATCH,
                    verified,
                    erased_verified,
                    0,
                )

            if row.event_bytes is None:
                if row.erased_at is None:
                    return VerifyResult(
                        False,
                        row.sequence_number,
                        VERIFY_FAILURE_MISSING_PAYLOAD,
                        verified,
                        erased_verified,
                        0,
                    )
                erased_verified += 1
            else:
                if not leaf_matches(row.event_bytes, row.leaf_hash, row.hash_algorithm):
                    return VerifyResult(
                        False,
                        row.sequence_number,
                        VERIFY_FAILURE_LEAF_MISMATCH,
                        verified,
                        erased_verified,
                        0,
                    )
                verified += 1

            if not chain_matches(row.prev_hash, row.leaf_hash, row.chain_hash, row.hash_algorithm):
                return VerifyResult(
                    False,
                    row.sequence_number,
                    VERIFY_FAILURE_CHAIN_MISMATCH,
                    verified,
                    erased_verified,
                    0,
                )

            expected_prev = row.chain_hash

        return VerifyResult(True, None, VERIFY_FAILURE_NONE, verified, erased_verified, 0)

    async def latest_checkpoint(self) -> AuditCheckpoint | None:
        result = await self._session.execute(
            select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_id.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def checkpoint_by_id(self, checkpoint_id: int) -> AuditCheckpoint | None:
        result = await self._session.execute(
            select(AuditCheckpoint).where(AuditCheckpoint.checkpoint_id == checkpoint_id)
        )
        return result.scalar_one_or_none()

    async def checkpoints_in_order(self) -> list[AuditCheckpoint]:
        result = await self._session.execute(
            select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_id.asc())
        )
        return list(result.scalars().all())

    async def event_at(self, sequence_number: int) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent).where(AuditEvent.sequence_number == sequence_number)
        )
        return result.scalar_one_or_none()

    async def append_checkpoint(
        self,
        tail_sequence_number: int,
        tail_chain_hash: bytes,
        tree_size: int,
        signature: bytes,
        key_id: str,
        prev_checkpoint_hash: bytes,
        payload: bytes,
        signature_algorithm: int,
        hash_algorithm: int = DEFAULT_HASH_ALGORITHM,
    ) -> AuditCheckpoint:
        checkpoint_hash = compute_checkpoint_hash(payload, hash_algorithm)
        row = AuditCheckpoint(
            tail_sequence_number=tail_sequence_number,
            tail_chain_hash=tail_chain_hash,
            tree_size=tree_size,
            hash_algorithm=hash_algorithm,
            signature_algorithm=signature_algorithm,
            signature=signature,
            key_id=key_id,
            prev_checkpoint_hash=prev_checkpoint_hash,
            checkpoint_hash=checkpoint_hash,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def genesis_checkpoint_hash(self) -> bytes:
        return GENESIS_CHECKPOINT_HASH

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(AuditEvent))
        return int(result.scalar_one())

    async def count_since(self, sequence_number: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.sequence_number > sequence_number)
        )
        return int(result.scalar_one())
