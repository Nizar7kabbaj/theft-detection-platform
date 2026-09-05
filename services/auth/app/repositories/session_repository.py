from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refresh_token import RefreshToken
from app.db.models.session import Session
from app.db.models.user import User


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str, source_ip: str, user_agent: str) -> Session:
        login_session = Session(
            user_id=user_id,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        self._session.add(login_session)
        await self._session.flush()
        await self._session.refresh(login_session)
        return login_session

    async def get_by_id(self, session_id: str) -> Session | None:
        result = await self._session.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def touch(self, session_id: str) -> None:
        await self._session.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked.is_(False))
            .values(last_used_at=func.now())
            .execution_options(synchronize_session=False)
        )

    async def idle_ids(self, cutoff: datetime) -> list[str]:
        result = await self._session.execute(
            select(Session.id).where(
                Session.revoked.is_(False),
                Session.last_used_at < cutoff,
            )
        )
        return list(result.scalars().all())

    async def revoke_ids(self, session_ids: list[str]) -> int:
        if not session_ids:
            return 0
        result = await self._session.execute(
            update(Session)
            .where(Session.id.in_(session_ids), Session.revoked.is_(False))
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)

    async def revoke(self, session_id: str) -> bool:
        result = await self._session.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked.is_(False))
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def last_used_by_user(self, user_ids: list[str]) -> dict[str, datetime]:
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(Session.user_id, func.max(Session.last_used_at))
            .where(Session.user_id.in_(user_ids))
            .group_by(Session.user_id)
        )
        return dict(result.all())

    async def count_live(self) -> int:
        resumable = (
            select(RefreshToken.session_id)
            .where(
                RefreshToken.session_id == Session.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > func.now(),
            )
            .exists()
        )
        result = await self._session.execute(
            select(func.count(func.distinct(Session.id)))
            .select_from(Session)
            .join(User, User.id == Session.user_id)
            .where(Session.revoked.is_(False), User.is_active.is_(True), resumable)
        )
        return int(result.scalar_one())

    async def live_ids_for_user(self, user_id: str) -> list[str]:
        result = await self._session.execute(
            select(Session.id).where(Session.user_id == user_id, Session.revoked.is_(False))
        )
        return list(result.scalars().all())

    async def revoke_all_for_user(self, user_id: str) -> int:
        result = await self._session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked.is_(False))
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)

    async def delete_for_user(self, user_id: str) -> int:
        result = await self._session.execute(delete(Session).where(Session.user_id == user_id))
        return int(result.rowcount)
