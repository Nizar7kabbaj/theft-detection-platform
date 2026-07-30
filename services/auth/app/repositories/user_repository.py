from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.user import User
from app.core.roles import Role


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self, username: str, password_hash: str, roles: list[str]
    ) -> User:
        validated = [str(Role(r)) for r in roles]
        user = User(
            username=username,
            password_hash=password_hash,
            roles=validated,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user
