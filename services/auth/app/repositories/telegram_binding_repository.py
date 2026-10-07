from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.telegram_binding import TelegramBinding


class TelegramBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: str) -> TelegramBinding | None:
        result = await self._session.execute(
            select(TelegramBinding).where(TelegramBinding.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_user_id: int) -> TelegramBinding | None:
        result = await self._session.execute(
            select(TelegramBinding).where(TelegramBinding.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def bind(self, user_id: str, telegram_user_id: int) -> None:
        statement = insert(TelegramBinding).values(
            user_id=user_id, telegram_user_id=telegram_user_id
        )
        statement = statement.on_conflict_do_update(
            index_elements=[TelegramBinding.user_id],
            set_={"telegram_user_id": telegram_user_id, "created_at": func.now()},
        )
        await self._session.execute(statement)

    async def unbind(self, user_id: str) -> int | None:
        result = await self._session.execute(
            delete(TelegramBinding)
            .where(TelegramBinding.user_id == user_id)
            .returning(TelegramBinding.telegram_user_id)
        )
        return result.scalar_one_or_none()
