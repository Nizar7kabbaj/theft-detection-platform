from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Index,
    Integer,
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
    event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, unique=True
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_service: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), index=True
    )
    actor: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("''"), index=True
    )
    severity: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), index=True
    )
    trace_id: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("''")
    )
    payload_kind: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), index=True
    )
    hash_algorithm: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    event_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    leaf_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    chain_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    erasure_reason: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index("ix_audit_events_occurred_seq", "occurred_at", "sequence_number"),
    )


class AuditChainSegment(Base):
    __tablename__ = "audit_chain_segments"

    segment_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    first_sequence_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True
    )
    last_sequence_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True
    )
    first_prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    terminal_chain_hash: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True
    )
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash_algorithm: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    covers_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    covers_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sealed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    checkpoint_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AuditCheckpoint(Base):
    __tablename__ = "audit_checkpoints"

    checkpoint_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tail_sequence_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True
    )
    tail_chain_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tree_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash_algorithm: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    signature_algorithm: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    prev_checkpoint_hash: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True
    )
    checkpoint_hash: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True
    )
