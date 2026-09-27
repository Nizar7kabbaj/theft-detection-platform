from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.core.database import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.users import CreateUserRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_user")


class SeedError(Exception):
    pass


def _parse_spec(spec: str) -> tuple[str, list[str]]:
    username, sep, roles = spec.partition(":")
    if not sep or not username:
        raise argparse.ArgumentTypeError(f"expected name:role[,role], got {spec!r}")
    return username, [role.strip() for role in roles.split(",") if role.strip()]


def _read_password(username: str, password_dir: Path | None) -> str:
    if password_dir is None:
        return getpass.getpass(f"password for {username}: ")
    path = password_dir / username
    try:
        return path.read_text(encoding="utf-8").rstrip("\r\n")
    except FileNotFoundError as exc:
        raise SeedError(f"no password file for {username}") from exc
    except OSError as exc:
        raise SeedError(f"password file for {username} is unreadable") from exc


def _load_users(
    specs: Sequence[tuple[str, list[str]]], password_dir: Path | None
) -> list[CreateUserRequest]:
    users: list[CreateUserRequest] = []
    seen: set[str] = set()
    failed = False
    for username, roles in specs:
        if username in seen:
            logger.error("user %s listed more than once", username)
            failed = True
            continue
        seen.add(username)
        try:
            if username != Path(username).name or username.startswith("."):
                raise SeedError(f"invalid username {username!r}")
            password = _read_password(username, password_dir)
            users.append(CreateUserRequest(username=username, password=password, roles=roles))
        except SeedError as exc:
            logger.error("%s", exc)
            failed = True
        except ValidationError as exc:
            for error in exc.errors(include_input=False, include_url=False):
                field = ".".join(str(part) for part in error["loc"])
                logger.error("user %s: %s: %s", username, field, error["msg"])
            failed = True
    if failed:
        raise SeedError("seed aborted, no user written")
    return users


async def _seed(users: Sequence[CreateUserRequest]) -> None:
    created = 0
    try:
        async with get_sessionmaker()() as session:
            repo = UserRepository(session)
            for user in users:
                if await repo.get_by_username(user.username) is not None:
                    logger.info("user %s exists, skipped", user.username)
                    continue
                roles = [str(role) for role in user.roles]
                await repo.create(
                    username=user.username,
                    password_hash=hash_password(user.password),
                    roles=roles,
                )
                created += 1
                logger.info("user %s created with roles %s", user.username, ",".join(roles))
            await session.commit()
    finally:
        await dispose_engine()
    logger.info("seed done, %d created, %d skipped", created, len(users) - created)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed_user", description="create users that do not exist yet"
    )
    parser.add_argument(
        "--user",
        dest="users",
        action="append",
        required=True,
        type=_parse_spec,
        metavar="NAME:ROLE[,ROLE]",
    )
    parser.add_argument("--password-dir", type=Path, default=None, metavar="DIR")
    args = parser.parse_args(argv)

    if args.password_dir is not None and not args.password_dir.is_dir():
        logger.error("password dir %s not found", args.password_dir)
        return 1
    try:
        users = _load_users(args.users, args.password_dir)
        asyncio.run(_seed(users))
    except SeedError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
