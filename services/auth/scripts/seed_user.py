from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys

from app.core.database import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.repositories.user_repository import UserRepository

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_user")

_MIN_PASSWORD_LENGTH = 8


def _read_password() -> str:
    password = os.environ.get("SEED_USER_PASSWORD")
    if password:
        return password
    return getpass.getpass("password for seed user: ")


async def _seed(username: str, roles: list[str], password: str) -> None:
    factory = get_sessionmaker()
    async with factory() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_username(username)
        if existing is not None:
            logger.info("user %s already exists, skipping", username)
            return
        user = await repo.create(
            username=username,
            password_hash=hash_password(password),
            roles=roles,
        )
        await session.commit()
        logger.info("seeded user %s with roles %s", user.username, user.roles)
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--roles", default="admin")
    args = parser.parse_args()

    password = _read_password()
    if len(password) < _MIN_PASSWORD_LENGTH:
        logger.error("password must be at least %d characters", _MIN_PASSWORD_LENGTH)
        sys.exit(1)

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    asyncio.run(_seed(args.username, roles, password))


if __name__ == "__main__":
    main()
