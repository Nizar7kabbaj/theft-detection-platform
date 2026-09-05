from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import Role
from app.db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, username: str, password_hash: str, roles: list[str]) -> User:
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

    def _filtered(
        self,
        *,
        search: str | None,
        role: str | None,
        is_active: bool | None,
    ) -> Select[tuple[User]]:
        stmt = select(User)
        if search:
            stmt = stmt.where(User.username.ilike(f"%{search}%"))
        if role is not None:
            stmt = stmt.where(User.roles.any(role))
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))
        return stmt

    async def list_users(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        stmt = (
            self._filtered(search=search, role=role, is_active=is_active)
            .order_by(User.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        inner = self._filtered(search=search, role=role, is_active=is_active).subquery()
        result = await self._session.execute(select(func.count()).select_from(inner))
        return int(result.scalar_one())

    async def count_by_active(self) -> tuple[int, int]:
        result = await self._session.execute(
            select(User.is_active, func.count()).group_by(User.is_active)
        )
        active = 0
        disabled = 0
        for flag, total in result.all():
            if flag:
                active = int(total)
            else:
                disabled = int(total)
        return active, disabled

    async def set_roles(self, user: User, roles: list[str]) -> User:
        user.roles = [str(Role(r)) for r in roles]
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def set_active(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def set_password_hash(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()
