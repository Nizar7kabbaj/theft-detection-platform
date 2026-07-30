from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.session import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: str, source_ip: str, user_agent: str
    ) -> Session:
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
        result = await self._session.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_id: str) -> None:
        await self._session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
