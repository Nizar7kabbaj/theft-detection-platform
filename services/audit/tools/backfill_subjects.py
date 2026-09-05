from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.database import dispose_owner_engine, get_owner_sessionmaker
from app.repositories.audit_repository import extract_subjects

logger = logging.getLogger("audit.backfill")

_BATCH = 500


async def _run() -> int:
    factory = get_owner_sessionmaker()
    cursor = 0
    updated = 0
    scanned = 0
    while True:
        async with factory() as session:
            await session.execute(text("SET LOCAL audit.maintenance = 'on'"))
            rows = await session.execute(
                text(
                    """
                    SELECT sequence_number, event_bytes
                    FROM audit_events
                    WHERE sequence_number > :cursor
                      AND subjects = '{}'
                      AND event_bytes IS NOT NULL
                    ORDER BY sequence_number
                    LIMIT :limit
                    """
                ),
                {"cursor": cursor, "limit": _BATCH},
            )
            batch = rows.all()
            if not batch:
                await session.rollback()
                break
            for sequence_number, payload in batch:
                cursor = sequence_number
                scanned += 1
                subjects = extract_subjects(payload)
                if not subjects:
                    continue
                await session.execute(
                    text(
                        "UPDATE audit_events SET subjects = :subjects "
                        "WHERE sequence_number = :sequence_number"
                    ),
                    {"subjects": subjects, "sequence_number": sequence_number},
                )
                updated += 1
            await session.commit()
        logger.info("scanned %d rows, %d carry subjects", scanned, updated)
    logger.info("backfill complete, scanned %d rows, updated %d", scanned, updated)
    await dispose_owner_engine()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
