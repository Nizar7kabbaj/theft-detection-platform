from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        jti: str,
        family_id: str,
        session_id: str,
        token_hash: str,
        expires_at: datetime,
        rotated_from: str | None = None,
    ) -> RefreshToken:
        token = RefreshToken(
            jti=jti,
            family_id=family_id,
            session_id=session_id,
            token_hash=token_hash,
            expires_at=expires_at,
            rotated_from=rotated_from,
        )
        self._session.add(token)
        await self._session.flush()
        await self._session.refresh(token)
        return token

    async def get_by_jti_and_hash(self, jti: str, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.jti == jti,
                RefreshToken.token_hash == token_hash,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        result = await self._session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        return result.scalar_one_or_none()

    async def mark_rotated(self, jti: str, replaced_by: str) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(revoked=True, rotated_at=datetime.now(UTC), replaced_by=replaced_by)
            .execution_options(synchronize_session=False)
        )

    async def revoke_family(self, family_id: str) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
