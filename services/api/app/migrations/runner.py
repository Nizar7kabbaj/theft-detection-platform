from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import logging
import os
import pkgutil
import socket
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import ModuleType
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import settings
from app.core.database import _resolve_mongodb_url
from app.migrations import versions

logger = logging.getLogger("migrations")

_TRACKING_COLLECTION = "_migrations"
_TRACKING_INDEX = "version_1"
_LOCK_COLLECTION = "_migrations_lock"
_LOCK_ID = "runner"
_LEASE_SECONDS = 120
_RENEW_SECONDS = 30
_WAIT_SECONDS = 240
_POLL_SECONDS = 2.0

Migration = tuple[int, str, ModuleType]


class LockLostError(RuntimeError):
    pass


def discover_versions() -> list[Migration]:
    found: list[Migration] = []
    for module_info in pkgutil.iter_modules(versions.__path__):
        module = importlib.import_module(f"{versions.__name__}.{module_info.name}")
        version = getattr(module, "VERSION", None)
        name = getattr(module, "NAME", None)
        if version is None or name is None:
            logger.warning("skipping %s: missing VERSION or NAME", module_info.name)
            continue
        found.append((version, name, module))
    found.sort(key=lambda item: item[0])
    return found


async def _applied_versions(db: AsyncIOMotorDatabase) -> set[int]:
    cursor = db[_TRACKING_COLLECTION].find({}, {"version": 1})
    return {doc["version"] async for doc in cursor}


async def _record(db: AsyncIOMotorDatabase, version: int, name: str, direction: str) -> None:
    if direction == "up":
        await db[_TRACKING_COLLECTION].insert_one(
            {
                "version": version,
                "name": name,
                "direction": "up",
                "applied_at": datetime.now(UTC),
            }
        )
    else:
        await db[_TRACKING_COLLECTION].delete_one({"version": version})


def _claim(owner: str) -> list[dict[str, object]]:
    free = {"$or": [{"$lt": ["$expires_at", "$$NOW"]}, {"$eq": ["$owner", owner]}]}
    expiry = {"$dateAdd": {"startDate": "$$NOW", "unit": "second", "amount": _LEASE_SECONDS}}
    return [
        {"$set": {"_claim": free}},
        {
            "$set": {
                "owner": {"$cond": ["$_claim", owner, "$owner"]},
                "renewed_at": {"$cond": ["$_claim", "$$NOW", "$renewed_at"]},
                "expires_at": {"$cond": ["$_claim", expiry, "$expires_at"]},
            }
        },
        {"$unset": "_claim"},
    ]


async def _claim_lock(db: AsyncIOMotorDatabase, owner: str) -> bool:
    try:
        doc = await db[_LOCK_COLLECTION].find_one_and_update(
            {"_id": _LOCK_ID},
            _claim(owner),
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return False
    return doc is not None and doc.get("owner") == owner


async def _try_acquire(db: AsyncIOMotorDatabase, owner: str) -> bool:
    return await _claim_lock(db, owner)


async def _renew(db: AsyncIOMotorDatabase, owner: str) -> bool:
    try:
        return await _claim_lock(db, owner)
    except PyMongoError as exc:
        logger.error("migration lock renewal failed: %s", exc)
        return False


async def _heartbeat(
    db: AsyncIOMotorDatabase,
    owner: str,
    guarded: asyncio.Task[object],
    lost: asyncio.Event,
) -> None:
    while True:
        await asyncio.sleep(_RENEW_SECONDS)
        if not await _renew(db, owner):
            lost.set()
            guarded.cancel()
            return


@contextlib.asynccontextmanager
async def _migration_lock(db: AsyncIOMotorDatabase) -> AsyncIterator[str]:
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WAIT_SECONDS
    announced = False
    while not await _try_acquire(db, owner):
        if loop.time() >= deadline:
            raise TimeoutError(f"migration lock still held after {_WAIT_SECONDS}s")
        if not announced:
            logger.info("migration lock held by another runner, waiting")
            announced = True
        await asyncio.sleep(_POLL_SECONDS)
    logger.info("migration lock taken by %s", owner)
    guarded = asyncio.current_task()
    if guarded is None:
        raise RuntimeError("migration lock needs a running task")
    lost = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat(db, owner, guarded, lost))
    try:
        yield owner
    except asyncio.CancelledError:
        if lost.is_set():
            guarded.uncancel()
            raise LockLostError("migration lock lost, run stopped") from None
        raise
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await db[_LOCK_COLLECTION].delete_one({"_id": _LOCK_ID, "owner": owner})
        logger.info("migration lock released")


async def _apply_up(
    db: AsyncIOMotorDatabase,
    discovered: list[Migration],
    applied: set[int],
    target: int | None,
) -> None:
    pending = [item for item in discovered if item[0] not in applied]
    if target is not None:
        pending = [item for item in pending if item[0] <= target]
    if not pending:
        logger.info("nothing to apply")
        return
    for version, name, module in pending:
        logger.info("applying %03d %s", version, name)
        await module.up(db)
        await _record(db, version, name, "up")
        logger.info("applied %03d %s", version, name)


async def _apply_down(
    db: AsyncIOMotorDatabase,
    discovered: list[Migration],
    applied: set[int],
    target: int | None,
) -> None:
    reversible = [item for item in reversed(discovered) if item[0] in applied]
    if target is not None:
        reversible = [item for item in reversible if item[0] >= target]
    if not reversible:
        logger.info("nothing to revert")
        return
    for version, name, module in reversible:
        logger.info("reverting %03d %s", version, name)
        await module.down(db)
        await _record(db, version, name, "down")
        logger.info("reverted %03d %s", version, name)


async def _run(direction: str, target: int | None) -> int:
    client: AsyncIOMotorClient = AsyncIOMotorClient(_resolve_mongodb_url(), tz_aware=True)
    db: AsyncIOMotorDatabase = client[settings.DATABASE_NAME]
    try:
        discovered = discover_versions()
        if not discovered:
            logger.info("no migrations found")
            return 0
        await db[_TRACKING_COLLECTION].create_index("version", name=_TRACKING_INDEX, unique=True)
        async with _migration_lock(db):
            applied = await _applied_versions(db)
            if direction == "up":
                await _apply_up(db, discovered, applied, target)
            else:
                await _apply_down(db, discovered, applied, target)
        return 0
    finally:
        client.close()


async def _status() -> int:
    client: AsyncIOMotorClient = AsyncIOMotorClient(_resolve_mongodb_url(), tz_aware=True)
    db: AsyncIOMotorDatabase = client[settings.DATABASE_NAME]
    try:
        discovered = discover_versions()
        applied = await _applied_versions(db)
        for version, name, _ in discovered:
            state = "applied" if version in applied else "pending"
            logger.info("%03d %s %s", version, name, state)
        return 0
    finally:
        client.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(prog="migrations")
    parser.add_argument("direction", choices=["up", "down", "status"])
    parser.add_argument("--target", type=int, default=None)
    args = parser.parse_args()

    try:
        if args.direction == "status":
            return asyncio.run(_status())
        return asyncio.run(_run(args.direction, args.target))
    except (LockLostError, TimeoutError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
