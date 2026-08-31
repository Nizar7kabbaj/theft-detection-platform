from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from app.core import database as database_module
from app.core.security import hash_password
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.server.grpc_gen import auth_pb2
from app.server.servicer import AuthServicer

_PASSWORD = "harness-password"
_UNKNOWN_SESSION = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
async def app_resources(redis_client, db_session) -> AsyncIterator[None]:
    yield
    await database_module.dispose_engine()
    database_module._sessionmaker = None


@pytest.fixture
async def live_session(db_session):
    user = await UserRepository(db_session).create(
        username="operator", password_hash=hash_password(_PASSWORD), roles=["operator", "viewer"]
    )
    login_session = await SessionRepository(db_session).create(
        user_id=user.id, source_ip="203.0.113.9", user_agent="harness"
    )
    await db_session.commit()
    return login_session


async def test_introspect_returns_active_session(live_session, grpc_context):
    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.active is True
    assert reply.user_id == live_session.user_id
    assert reply.source_ip == "203.0.113.9"
    assert reply.user_agent == "harness"


async def test_introspect_returns_roles(live_session, grpc_context):
    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=live_session.id), grpc_context
    )

    assert list(reply.roles) == ["operator", "viewer"]


async def test_introspect_reports_timestamps(live_session, grpc_context):
    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.issued_at.seconds > 0
    assert reply.last_used_at.seconds > 0


async def test_introspect_unknown_session_is_inactive(grpc_context):
    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=_UNKNOWN_SESSION), grpc_context
    )

    assert reply.active is False
    assert reply.user_id == ""


async def test_introspect_revoked_session_is_inactive(live_session, db_session, grpc_context):
    await db_session.execute(text("update sessions set revoked = true"))
    await db_session.commit()

    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.active is False
    assert reply.user_id == live_session.user_id


async def test_introspect_disabled_user_reports_no_roles(live_session, db_session, grpc_context):
    await db_session.execute(text("update users set is_active = false"))
    await db_session.commit()

    reply = await AuthServicer().IntrospectSession(
        auth_pb2.IntrospectSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.active is True
    assert list(reply.roles) == []


async def test_revoke_marks_the_session(live_session, db_session, grpc_context):
    reply = await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.revoked is True
    assert reply.revoked_at.seconds > 0

    result = await db_session.execute(text("select revoked from sessions"))
    assert result.scalar_one() is True


async def test_revoke_enqueues_an_audit_event(live_session, db_session, grpc_context):
    await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 1


async def test_revoke_with_actor_enqueues_two_events(live_session, db_session, grpc_context):
    await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id, revoked_by=live_session.user_id),
        grpc_context,
    )

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 2


async def test_revoke_publishes_to_the_revocation_key(live_session, redis_client, grpc_context):
    await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    assert await redis_client.exists(f"revoked:sid:{live_session.id}") == 1


async def test_revoke_unknown_session_reports_not_revoked(grpc_context):
    reply = await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=_UNKNOWN_SESSION), grpc_context
    )

    assert reply.revoked is False


async def test_revoke_unknown_session_enqueues_nothing(db_session, grpc_context):
    await AuthServicer().RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=_UNKNOWN_SESSION), grpc_context
    )

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 0


async def test_second_revoke_still_reports_the_session_existed(
    live_session, db_session, grpc_context
):
    servicer = AuthServicer()
    await servicer.RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    reply = await servicer.RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    assert reply.revoked is True


async def test_second_revoke_enqueues_no_further_events(live_session, db_session, grpc_context):
    servicer = AuthServicer()
    await servicer.RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )
    await servicer.RevokeSession(
        auth_pb2.RevokeSessionRequest(session_id=live_session.id), grpc_context
    )

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 1
