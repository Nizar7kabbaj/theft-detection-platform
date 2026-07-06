from __future__ import annotations
import argparse
import asyncio
import importlib
import logging
import pkgutil
import sys
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.shared.config import settings
from app.core.database import _resolve_mongodb_url
from app.migrations import versions
logger = logging.getLogger("migrations")
_TRACKING_COLLECTION = "_notification_migrations"
def _discover_versions() -> list[tuple[int, str, object]]:
    found: list[tuple[int, str, object]] = []
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
        await db[_TRACKING_COLLECTION].insert_one({
            "version": version,
            "name": name,
            "direction": "up",
            "applied_at": datetime.now(timezone.utc),
        })
    else:
        await db[_TRACKING_COLLECTION].delete_one({"version": version})
async def _run(direction: str, target: int | None) -> int:
    client: AsyncIOMotorClient = AsyncIOMotorClient(_resolve_mongodb_url())
    db: AsyncIOMotorDatabase = client[settings.DATABASE_NAME]
    try:
        discovered = _discover_versions()
        if not discovered:
            logger.info("no migrations found")
            return 0
        applied = await _applied_versions(db)
        if direction == "up":
            pending = [item for item in discovered if item[0] not in applied]
            if target is not None:
                pending = [item for item in pending if item[0] <= target]
            if not pending:
                logger.info("nothing to apply")
                return 0
            for version, name, module in pending:
                logger.info("applying %03d %s", version, name)
                await module.up(db)
                await _record(db, version, name, "up")
                logger.info("applied %03d %s", version, name)
            return 0
        if direction == "down":
            reversible = [item for item in reversed(discovered) if item[0] in applied]
            if target is not None:
                reversible = [item for item in reversible if item[0] >= target]
            if not reversible:
                logger.info("nothing to revert")
                return 0
            for version, name, module in reversible:
                logger.info("reverting %03d %s", version, name)
                await module.down(db)
                await _record(db, version, name, "down")
                logger.info("reverted %03d %s", version, name)
            return 0
        logger.error("unknown direction: %s", direction)
        return 2
    finally:
        client.close()
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", force=True)
    parser = argparse.ArgumentParser(prog="migrations")
    parser.add_argument("direction", choices=["up", "down", "status"])
    parser.add_argument("--target", type=int, default=None)
    args = parser.parse_args()
    if args.direction == "status":
        return asyncio.run(_status())
    return asyncio.run(_run(args.direction, args.target))
async def _status() -> int:
    client: AsyncIOMotorClient = AsyncIOMotorClient(_resolve_mongodb_url())
    db: AsyncIOMotorDatabase = client[settings.DATABASE_NAME]
    try:
        discovered = _discover_versions()
        applied = await _applied_versions(db)
        if not discovered:
            logger.info("no migrations found")
            return 0
        for version, name, _ in discovered:
            state = "applied" if version in applied else "pending"
            logger.info("%03d %s %s", version, name, state)
        return 0
    finally:
        client.close()
