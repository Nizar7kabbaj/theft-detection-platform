from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.audit_event import AuditChainSegment, AuditEvent
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


class RetentionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SegmentCandidate:
    first_sequence_number: int
    last_sequence_number: int
    first_prev_hash: bytes
    terminal_chain_hash: bytes
    row_count: int
    hash_algorithm: int
    covers_from: datetime
    covers_to: datetime


@dataclass(frozen=True, slots=True)
class SealOutcome:
    segment_id: int
    first_sequence_number: int
    last_sequence_number: int
    row_count: int
    terminal_chain_hash: bytes
    covers_from: datetime
    covers_to: datetime
    checkpoint_id: int | None


def _now() -> datetime:
    return datetime.now(UTC)


def retention_cutoff(now: datetime | None = None) -> datetime:
    settings = get_settings()
    return (now or _now()) - timedelta(days=settings.retention_days)


class RetentionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events = AuditRepository(session)

    async def _enter_maintenance(self) -> None:
        await self._session.execute(text("SET LOCAL audit.maintenance = 'on'"))

    async def _sealed_through(self) -> int:
        result = await self._session.execute(
            select(func.max(AuditChainSegment.last_sequence_number))
        )
        return result.scalar_one_or_none() or 0

    async def _oldest_live(self, after_sequence_number: int) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.sequence_number > after_sequence_number)
            .order_by(AuditEvent.sequence_number.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_segment(
        self, now: datetime | None = None
    ) -> SegmentCandidate | None:
        settings = get_settings()
        cutoff = retention_cutoff(now)
        sealed_through = await self._sealed_through()

        oldest = await self._oldest_live(sealed_through)
        if oldest is None:
            return None

        window_end = oldest.persisted_at + timedelta(
            days=settings.segment_interval_days
        )
        if window_end > cutoff:
            return None

        rows = (
            (
                await self._session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.sequence_number > sealed_through)
                    .where(AuditEvent.persisted_at < window_end)
                    .order_by(AuditEvent.sequence_number.asc())
                    .limit(settings.retention_max_rows_per_run)
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            return None

        head = rows[0]
        tail = rows[-1]

        successor = await self._oldest_live(tail.sequence_number)
        if successor is None:
            return None
        if successor.prev_hash != tail.chain_hash:
            raise RetentionError(
                f"chain linkage broken at boundary {tail.sequence_number}, "
                "refusing to seal"
            )

        algorithms = {row.hash_algorithm for row in rows}
        if len(algorithms) != 1:
            raise RetentionError(
                "mixed hash algorithms in range "
                f"{head.sequence_number}-{tail.sequence_number}"
            )

        return SegmentCandidate(
            first_sequence_number=head.sequence_number,
            last_sequence_number=tail.sequence_number,
            first_prev_hash=head.prev_hash,
            terminal_chain_hash=tail.chain_hash,
            row_count=len(rows),
            hash_algorithm=algorithms.pop(),
            covers_from=head.persisted_at,
            covers_to=tail.persisted_at,
        )

    async def seal_and_drop(self, candidate: SegmentCandidate) -> SealOutcome:
        await self._events.lock_chain()
        await self._enter_maintenance()

        checkpoint = await self._events.latest_checkpoint()
        checkpoint_id: int | None = None
        if checkpoint is not None:
            if checkpoint.tail_sequence_number < candidate.last_sequence_number:
                raise RetentionError(
                    "latest checkpoint at "
                    f"{checkpoint.tail_sequence_number} does not cover "
                    f"{candidate.last_sequence_number}, refusing to seal"
                )
            checkpoint_id = checkpoint.checkpoint_id

        result = await self._session.execute(
            text(
                """
                INSERT INTO audit_chain_segments (
                    first_sequence_number, last_sequence_number, first_prev_hash,
                    terminal_chain_hash, row_count, hash_algorithm,
                    covers_from, covers_to, checkpoint_id
                ) VALUES (
                    :first_sequence_number, :last_sequence_number, :first_prev_hash,
                    :terminal_chain_hash, :row_count, :hash_algorithm,
                    :covers_from, :covers_to, :checkpoint_id
                )
                RETURNING segment_id
                """
            ),
            {
                "first_sequence_number": candidate.first_sequence_number,
                "last_sequence_number": candidate.last_sequence_number,
                "first_prev_hash": candidate.first_prev_hash,
                "terminal_chain_hash": candidate.terminal_chain_hash,
                "row_count": candidate.row_count,
                "hash_algorithm": candidate.hash_algorithm,
                "covers_from": candidate.covers_from,
                "covers_to": candidate.covers_to,
                "checkpoint_id": checkpoint_id,
            },
        )
        segment_id = result.scalar_one()

        deleted = await self._session.execute(
            delete(AuditEvent)
            .where(AuditEvent.sequence_number >= candidate.first_sequence_number)
            .where(AuditEvent.sequence_number <= candidate.last_sequence_number)
        )
        if deleted.rowcount != candidate.row_count:
            raise RetentionError(
                f"expected to drop {candidate.row_count} rows, "
                f"dropped {deleted.rowcount}"
            )

        survivor = await self._oldest_live(candidate.last_sequence_number)
        if survivor is None:
            raise RetentionError("no surviving head after drop, refusing to commit")
        if survivor.prev_hash != candidate.terminal_chain_hash:
            raise RetentionError("surviving head does not link to sealed terminal hash")

        logger.info(
            "sealed segment %d covering %d rows, sequences %d to %d",
            segment_id,
            candidate.row_count,
            candidate.first_sequence_number,
            candidate.last_sequence_number,
        )

        return SealOutcome(
            segment_id=segment_id,
            first_sequence_number=candidate.first_sequence_number,
            last_sequence_number=candidate.last_sequence_number,
            row_count=candidate.row_count,
            terminal_chain_hash=candidate.terminal_chain_hash,
            covers_from=candidate.covers_from,
            covers_to=candidate.covers_to,
            checkpoint_id=checkpoint_id,
        )
