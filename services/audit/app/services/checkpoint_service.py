from __future__ import annotations

import asyncio
import logging

from app.core.chain import (
    GENESIS_CHECKPOINT_HASH,
    checkpoint_matches,
)
from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.signing import build_checkpoint_payload, get_signer
from app.repositories.audit_repository import (
    VERIFY_FAILURE_CHECKPOINT_DIVERGENCE,
    VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID,
    VERIFY_FAILURE_NONE,
    AuditRepository,
)

logger = logging.getLogger(__name__)


class CheckpointResult:
    __slots__ = ("break_at_checkpoint_id", "checkpoints_verified", "failure_kind")

    def __init__(
        self,
        failure_kind: int,
        checkpoints_verified: int,
        break_at_checkpoint_id: int | None,
    ) -> None:
        self.failure_kind = failure_kind
        self.checkpoints_verified = checkpoints_verified
        self.break_at_checkpoint_id = break_at_checkpoint_id


async def create_checkpoint() -> int | None:
    signer = get_signer()
    factory = get_sessionmaker()

    async with factory() as db:
        events = AuditRepository(db)
        await events.lock_chain()

        tail = await events.tail_state()
        if tail.tree_size == 0:
            return None

        previous = await events.latest_checkpoint()
        if previous is not None:
            if previous.tail_sequence_number == tail.tail_sequence_number:
                return None
            prev_hash = previous.checkpoint_hash
        else:
            prev_hash = GENESIS_CHECKPOINT_HASH

        payload = build_checkpoint_payload(
            key_id=signer.key_id,
            tree_size=tail.tree_size,
            tail_sequence_number=tail.tail_sequence_number,
            tail_chain_hash=tail.prev_hash,
            prev_checkpoint_hash=prev_hash,
            signature_algorithm=signer.signature_algorithm,
        )
        signature = signer.sign(payload)

        row = await events.append_checkpoint(
            tail_sequence_number=tail.tail_sequence_number,
            tail_chain_hash=tail.prev_hash,
            tree_size=tail.tree_size,
            signature=signature,
            key_id=signer.key_id,
            prev_checkpoint_hash=prev_hash,
            payload=payload,
            signature_algorithm=signer.signature_algorithm,
        )
        await db.commit()
        logger.info(
            "checkpoint written at sequence %s covering %s events",
            tail.tail_sequence_number,
            tail.tree_size,
        )
        return row.checkpoint_id


async def verify_checkpoints(repository: AuditRepository) -> CheckpointResult:
    signer = get_signer()
    rows = await repository.checkpoints_in_order()
    expected_prev = GENESIS_CHECKPOINT_HASH
    verified = 0

    for row in rows:
        payload = build_checkpoint_payload(
            key_id=row.key_id,
            tree_size=row.tree_size,
            tail_sequence_number=row.tail_sequence_number,
            tail_chain_hash=row.tail_chain_hash,
            prev_checkpoint_hash=row.prev_checkpoint_hash,
            signature_algorithm=row.signature_algorithm,
            hash_algorithm=row.hash_algorithm,
        )

        if not checkpoint_matches(payload, row.checkpoint_hash, row.hash_algorithm):
            return CheckpointResult(
                VERIFY_FAILURE_CHECKPOINT_DIVERGENCE, verified, row.checkpoint_id
            )

        if row.prev_checkpoint_hash != expected_prev:
            return CheckpointResult(
                VERIFY_FAILURE_CHECKPOINT_DIVERGENCE, verified, row.checkpoint_id
            )

        if not signer.verify(payload, row.signature, row.key_id):
            return CheckpointResult(
                VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID, verified, row.checkpoint_id
            )

        event = await repository.event_at(row.tail_sequence_number)
        if event is not None and event.chain_hash != row.tail_chain_hash:
            return CheckpointResult(
                VERIFY_FAILURE_CHECKPOINT_DIVERGENCE, verified, row.checkpoint_id
            )

        expected_prev = row.checkpoint_hash
        verified += 1

    return CheckpointResult(VERIFY_FAILURE_NONE, verified, None)


async def checkpoint_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    factory = get_sessionmaker()
    last_sequence = 0

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.checkpoint_interval_seconds)
            break
        except TimeoutError:
            pass

        try:
            async with factory() as db:
                pending = await AuditRepository(db).count_since(last_sequence)
            if pending == 0:
                continue
            checkpoint_id = await create_checkpoint()
            if checkpoint_id is not None:
                async with factory() as db:
                    row = await AuditRepository(db).checkpoint_by_id(checkpoint_id)
                    if row is not None:
                        last_sequence = row.tail_sequence_number
        except Exception as exc:
            logger.error("checkpoint cycle failed: %s", exc)


async def append_hook(appended_since_checkpoint: int) -> bool:
    settings = get_settings()
    return appended_since_checkpoint >= settings.checkpoint_interval_events
