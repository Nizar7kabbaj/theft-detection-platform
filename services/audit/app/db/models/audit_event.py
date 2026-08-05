from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    LargeBinary,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    sequence_number: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_service: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("''"), index=True
    )
    actor: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default=text("''"), index=True
    )
    severity: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), index=True
    )
    trace_id: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("''")
    )
    event_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    chain_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
