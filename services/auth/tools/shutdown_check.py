from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.core.database import dispose_engine, get_sessionmaker
from app.core.redis import close_redis, get_redis


async def _open_connections() -> None:
    factory = get_sessionmaker()
    async with factory() as session:
        await session.execute(text("select 1"))
    await get_redis().set("login:fail:shutdown-check", 1, ex=60)
    await get_redis().delete("login:fail:shutdown-check")


async def _run(hold_seconds: int, release: bool) -> None:
    await _open_connections()
    print("connections open", flush=True)
    if release:
        await close_redis()
        await dispose_engine()
        print("release called", flush=True)
    else:
        print("release skipped", flush=True)
    print(f"holding {hold_seconds}s", flush=True)
    await asyncio.sleep(hold_seconds)
    print("done", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold", type=int, default=30)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.hold, args.release))
    return 0


if __name__ == "__main__":
    sys.exit(main())
