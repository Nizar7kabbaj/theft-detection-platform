from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

_HASH = "$argon2id$v=19$m=8192,t=1,p=1$c2FsdHNhbHQ$0000000000000000000000000000"


async def _user(session, username: str = "operator"):
    user = await UserRepository(session).create(
        username=username, password_hash=_HASH, roles=["operator"]
    )
    await session.commit()
    return user


async def _session_for(db_session, username: str = "operator"):
    user = await _user(db_session, username)
    login_session = await SessionRepository(db_session).create(
        user_id=user.id, source_ip="203.0.113.9", user_agent="harness"
    )
    await db_session.commit()
    return login_session


async def _token(db_session, login_session, jti: str | None = None, family: str | None = None):
    token_jti = jti or str(uuid.uuid4())
    token = await RefreshTokenRepository(db_session).create(
        jti=token_jti,
        family_id=family or token_jti,
        session_id=login_session.id,
        token_hash=f"hash-{token_jti}",
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    await db_session.commit()
    return token


async def test_create_session_generates_id(db_session):
    login_session = await _session_for(db_session)

    assert uuid.UUID(login_session.id)


async def test_create_session_stores_client_details(db_session):
    login_session = await _session_for(db_session)

    assert login_session.source_ip == "203.0.113.9"
    assert login_session.user_agent == "harness"
    assert login_session.revoked is False


async def test_session_timestamps_are_populated(db_session):
    login_session = await _session_for(db_session)

    assert login_session.created_at.tzinfo is not None
    assert login_session.last_used_at is not None


async def test_get_by_id_round_trips(db_session):
    login_session = await _session_for(db_session)
    found = await SessionRepository(db_session).get_by_id(login_session.id)

    assert found is not None
    assert found.id == login_session.id


async def test_get_by_id_returns_none_for_unknown_session(db_session):
    assert await SessionRepository(db_session).get_by_id(str(uuid.uuid4())) is None


async def test_revoke_marks_session_and_reports_change(db_session):
    login_session = await _session_for(db_session)
    session_id = login_session.id
    repo = SessionRepository(db_session)

    assert await repo.revoke(session_id) is True
    await db_session.commit()
    db_session.expire_all()

    found = await repo.get_by_id(session_id)
    assert found.revoked is True


async def test_second_revoke_reports_no_change(db_session):
    login_session = await _session_for(db_session)
    repo = SessionRepository(db_session)
    await repo.revoke(login_session.id)
    await db_session.commit()

    assert await repo.revoke(login_session.id) is False


async def test_revoke_unknown_session_reports_no_change(db_session):
    assert await SessionRepository(db_session).revoke(str(uuid.uuid4())) is False


async def test_user_agent_longer_than_column_is_rejected(db_session):
    user = await _user(db_session, "operator-long")

    with pytest.raises(Exception, match="too long"):
        await SessionRepository(db_session).create(
            user_id=user.id, source_ip="203.0.113.9", user_agent="a" * 600
        )


async def test_refresh_token_persists_with_defaults(db_session):
    login_session = await _session_for(db_session)
    token = await _token(db_session, login_session)

    assert token.revoked is False
    assert token.rotated_at is None
    assert token.replaced_by is None
    assert token.created_at is not None


async def test_refresh_token_requires_existing_session(db_session):
    with pytest.raises(IntegrityError):
        await RefreshTokenRepository(db_session).create(
            jti=str(uuid.uuid4()),
            family_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            token_hash="orphan-hash",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )


async def test_duplicate_token_hash_is_rejected(db_session):
    login_session = await _session_for(db_session)
    await _token(db_session, login_session, jti="11111111-1111-1111-1111-111111111111")

    with pytest.raises(IntegrityError):
        await RefreshTokenRepository(db_session).create(
            jti=str(uuid.uuid4()),
            family_id=str(uuid.uuid4()),
            session_id=login_session.id,
            token_hash="hash-11111111-1111-1111-1111-111111111111",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )


async def test_get_by_jti_and_hash_requires_both(db_session):
    login_session = await _session_for(db_session)
    token = await _token(db_session, login_session)
    repo = RefreshTokenRepository(db_session)

    assert await repo.get_by_jti_and_hash(token.jti, token.token_hash) is not None
    assert await repo.get_by_jti_and_hash(token.jti, "wrong-hash") is None
    assert await repo.get_by_jti_and_hash(str(uuid.uuid4()), token.token_hash) is None


async def test_mark_rotated_sets_revocation_and_successor(db_session):
    login_session = await _session_for(db_session)
    token = await _token(db_session, login_session)
    token_jti = token.jti
    successor = str(uuid.uuid4())
    repo = RefreshTokenRepository(db_session)

    await repo.mark_rotated(token_jti, successor)
    await db_session.commit()
    db_session.expire_all()

    rotated = await repo.get_by_jti(token_jti)
    assert rotated.revoked is True
    assert rotated.replaced_by == successor
    assert rotated.rotated_at is not None


async def test_revoke_family_revokes_every_member(db_session):
    login_session = await _session_for(db_session)
    family = str(uuid.uuid4())
    first_jti = (await _token(db_session, login_session, family=family)).jti
    second_jti = (await _token(db_session, login_session, family=family)).jti
    other_jti = (await _token(db_session, login_session)).jti
    repo = RefreshTokenRepository(db_session)

    await repo.revoke_family(family)
    await db_session.commit()
    db_session.expire_all()

    assert (await repo.get_by_jti(first_jti)).revoked is True
    assert (await repo.get_by_jti(second_jti)).revoked is True
    assert (await repo.get_by_jti(other_jti)).revoked is False


async def test_deleting_session_cascades_to_tokens(db_session):
    login_session = await _session_for(db_session)
    token = await _token(db_session, login_session)

    await db_session.execute(text("delete from sessions where id = :id"), {"id": login_session.id})
    await db_session.commit()

    assert await RefreshTokenRepository(db_session).get_by_jti(token.jti) is None
