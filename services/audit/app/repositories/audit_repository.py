from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chain import GENESIS_PREV_HASH, compute_chain_hash
from app.db.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)

_CHAIN_LOCK_KEY = 8410723461907712001


class AppendResult:
    __slots__ = ("sequence_number", "chain_hash", "persisted_at", "duplicate")

    def __init__(
        self,
        sequence_number: int,
        chain_hash: bytes,
        persisted_at: datetime,
        duplicate: bool,
    ) -> None:
        self.sequence_number = sequence_number
        self.chain_hash = chain_hash
        self.persisted_at = persisted_at
        self.duplicate = duplicate


class VerifyResult:
    __slots__ = ("chain_intact", "break_at_sequence_number", "events_verified")

    def __init__(
        self,
        chain_intact: bool,
        break_at_sequence_number: int | None,
        events_verified: int,
    ) -> None:
        self.chain_intact = chain_intact
        self.break_at_sequence_number = break_at_sequence_number
        self.events_verified = events_verified


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _lock_chain(self) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CHAIN_LOCK_KEY}
        )

    async def _find_by_event_id(self, event_id: str) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent).where(AuditEvent.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def _tail_hash(self) -> bytes:
        result = await self._session.execute(
            select(AuditEvent.chain_hash)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        tail = result.scalar_one_or_none()
        return tail if tail is not None else GENESIS_PREV_HASH

    async def append(
        self,
        event_id: str,
        occurred_at: datetime,
        source_service: str,
        actor: str,
        severity: int,
        trace_id: str,
        event_bytes: bytes,
    ) -> AppendResult:
        existing = await self._find_by_event_id(event_id)
        if existing is not None:
            return AppendResult(
                existing.sequence_number,
                existing.chain_hash,
                existing.persisted_at,
                True,
            )

        await self._lock_chain()

        existing = await self._find_by_event_id(event_id)
        if existing is not None:
            return AppendResult(
                existing.sequence_number,
                existing.chain_hash,
                existing.persisted_at,
                True,
            )

        prev_hash = await self._tail_hash()
        chain_hash = compute_chain_hash(prev_hash, event_bytes)

        row = AuditEvent(
            event_id=event_id,
            occurred_at=occurred_at,
            source_service=source_service,
            actor=actor,
            severity=severity,
            trace_id=trace_id,
            event_bytes=event_bytes,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)

        return AppendResult(
            row.sequence_number, row.chain_hash, row.persisted_at, False
        )

    def _apply_filters(
        self,
        stmt: Select[tuple[AuditEvent]],
        from_time: datetime | None,
        to_time: datetime | None,
        source_service: str,
        actor: str,
        min_severity: int,
    ) -> Select[tuple[AuditEvent]]:
        if from_time is not None:
            stmt = stmt.where(AuditEvent.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(AuditEvent.occurred_at < to_time)
        if source_service:
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
        source_service: str,
        actor: str,
        min_severity: int,
        page_size: int,
        after_sequence_number: int | None,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent)
        stmt = self._apply_filters(
            stmt, from_time, to_time, source_service, actor, min_severity
        )
        if after_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number > after_sequence_number)
        stmt = stmt.order_by(AuditEvent.sequence_number.asc()).limit(page_size)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def verify(
        self, from_sequence_number: int | None, to_sequence_number: int | None
    ) -> VerifyResult:
        stmt = select(AuditEvent).order_by(AuditEvent.sequence_number.asc())
        if from_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number >= from_sequence_number)
        if to_sequence_number is not None:
            stmt = stmt.where(AuditEvent.sequence_number <= to_sequence_number)

        expected_prev: bytes | None = None
        verified = 0

        stream = await self._session.stream_scalars(stmt)
        async for row in stream:
            if expected_prev is None:
                if from_sequence_number is None and row.prev_hash != GENESIS_PREV_HASH:
                    return VerifyResult(False, row.sequence_number, verified)
            elif row.prev_hash != expected_prev:
                return VerifyResult(False, row.sequence_number, verified)

            recomputed = compute_chain_hash(row.prev_hash, row.event_bytes)
            if recomputed != row.chain_hash:
                return VerifyResult(False, row.sequence_number, verified)

            expected_prev = row.chain_hash
            verified += 1

        return VerifyResult(True, None, verified)

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(AuditEvent)
        )
        return int(result.scalar_one())
