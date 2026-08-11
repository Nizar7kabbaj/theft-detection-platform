from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_outbox import AuditOutbox, AuditOutboxDead


@dataclass(frozen=True, slots=True)
class PendingEvent:
    id: int
    event_id: str
    event_bytes: bytes
    occurred_at: datetime
    attempts: int
    created_at: datetime


class AuditOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, event_id: str, event_bytes: bytes, occurred_at: datetime) -> None:
        self._session.add(
            AuditOutbox(
                event_id=event_id,
                event_bytes=event_bytes,
                occurred_at=occurred_at,
            )
        )
        await self._session.flush()

    async def claim(self, limit: int) -> list[PendingEvent]:
        result = await self._session.execute(
            text(
                """
                SELECT id, event_id, event_bytes, occurred_at, attempts, created_at
                FROM audit_outbox
                WHERE next_attempt_at <= now()
                ORDER BY id
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": limit},
        )
        return [
            PendingEvent(
                id=row[0],
                event_id=str(row[1]),
                event_bytes=row[2],
                occurred_at=row[3],
                attempts=row[4],
                created_at=row[5],
            )
            for row in result.all()
        ]

    async def release(self, outbox_id: int) -> None:
        await self._session.execute(delete(AuditOutbox).where(AuditOutbox.id == outbox_id))

    async def defer(self, outbox_id: int, next_attempt_at: datetime) -> None:
        await self._session.execute(
            update(AuditOutbox)
            .where(AuditOutbox.id == outbox_id)
            .values(attempts=AuditOutbox.attempts + 1, next_attempt_at=next_attempt_at)
            .execution_options(synchronize_session=False)
        )

    async def bury(self, pending: PendingEvent, last_status: int) -> None:
        self._session.add(
            AuditOutboxDead(
                event_id=pending.event_id,
                event_bytes=pending.event_bytes,
                occurred_at=pending.occurred_at,
                attempts=pending.attempts + 1,
                last_status=last_status,
                created_at=pending.created_at,
            )
        )
        await self._session.execute(delete(AuditOutbox).where(AuditOutbox.id == pending.id))
        await self._session.flush()

    async def pending_count(self) -> int:
        result = await self._session.execute(text("SELECT count(*) FROM audit_outbox"))
        return int(result.scalar_one())

    async def oldest_pending_age_seconds(self) -> float:
        result = await self._session.execute(
            text("SELECT extract(epoch FROM now() - min(created_at)) FROM audit_outbox")
        )
        value = result.scalar_one()
        return 0.0 if value is None else float(value)
