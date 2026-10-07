from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
from sqlalchemy import func, select

from app.core import database as database_module
from app.core.redis import store_telegram_link
from app.core.security import hash_password
from app.core.telegram_link import hash_link_token, new_link_token
from app.db.models.audit_outbox import AuditOutbox
from app.repositories.telegram_binding_repository import TelegramBindingRepository
from app.repositories.user_repository import UserRepository
from app.server import servicer as servicer_module
from app.server.grpc_gen import auth_pb2, common_pb2
from app.server.servicer import AuthServicer
from tests.conftest import FakeAbortError

TELEGRAM_ID = 777
OTHER_TELEGRAM_ID = 888


@pytest.fixture(autouse=True)
async def app_resources(redis_client, db_session) -> AsyncIterator[None]:
    yield
    await database_module.dispose_engine()
    database_module._sessionmaker = None


@pytest.fixture
def caller(monkeypatch) -> Callable[[int], None]:
    def set_caller(service: int) -> None:
        monkeypatch.setattr(servicer_module, "peer_service", lambda: service)

    set_caller(common_pb2.SOURCE_SERVICE_NOTIFICATION)
    return set_caller


async def _user(db_session, username: str = "operator", active: bool = True):
    users = UserRepository(db_session)
    user = await users.create(
        username=username, password_hash=hash_password("harness-password"), roles=["operator"]
    )
    if not active:
        await users.set_active(user, False)
    await db_session.commit()
    return user


async def _link(user_id: str) -> str:
    token = new_link_token()
    await store_telegram_link(user_id, hash_link_token(token), 600)
    return token


async def _bind(token: str, grpc_context, telegram_user_id: int = TELEGRAM_ID):
    request = auth_pb2.BindTelegramRequest(link_token=token, telegram_user_id=telegram_user_id)
    return await AuthServicer().BindTelegram(request, grpc_context)


async def _audit_rows(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(AuditOutbox))


async def test_a_link_binds_once_and_is_audited(db_session, grpc_context, caller):
    user = await _user(db_session)
    token = await _link(user.id)

    first = await _bind(token, grpc_context)
    second = await _bind(token, grpc_context)

    assert first.status == auth_pb2.BIND_TELEGRAM_STATUS_BOUND
    assert first.username == "operator"
    assert second.status == auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID
    binding = await TelegramBindingRepository(db_session).get_for_user(user.id)
    assert binding is not None
    assert binding.telegram_user_id == TELEGRAM_ID
    assert await _audit_rows(db_session) == 1


async def test_a_new_link_revokes_the_previous_one(db_session, grpc_context, caller):
    user = await _user(db_session)
    old = await _link(user.id)
    new = await _link(user.id)

    assert (await _bind(old, grpc_context)).status == auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID
    assert (await _bind(new, grpc_context)).status == auth_pb2.BIND_TELEGRAM_STATUS_BOUND


async def test_relinking_the_same_account_adds_no_audit(db_session, grpc_context, caller):
    user = await _user(db_session)
    await _bind(await _link(user.id), grpc_context)
    again = await _bind(await _link(user.id), grpc_context)

    assert again.status == auth_pb2.BIND_TELEGRAM_STATUS_BOUND
    assert await _audit_rows(db_session) == 1


async def test_an_account_linked_to_someone_else_is_refused(db_session, grpc_context, caller):
    first = await _user(db_session, "first")
    second = await _user(db_session, "second")
    await _bind(await _link(first.id), grpc_context)

    reply = await _bind(await _link(second.id), grpc_context)

    assert reply.status == auth_pb2.BIND_TELEGRAM_STATUS_ACCOUNT_IN_USE
    assert await TelegramBindingRepository(db_session).get_for_user(second.id) is None


async def test_a_disabled_user_cannot_link(db_session, grpc_context, caller):
    user = await _user(db_session, active=False)
    reply = await _bind(await _link(user.id), grpc_context)
    assert reply.status == auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID


async def test_a_malformed_token_is_invalid(grpc_context, caller):
    reply = await _bind("not-a-token", grpc_context)
    assert reply.status == auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID


async def test_only_notification_may_bind(grpc_context, caller):
    caller(common_pb2.SOURCE_SERVICE_API)
    with pytest.raises(FakeAbortError):
        await _bind(new_link_token(), grpc_context)


async def test_lookup_resolves_a_linked_operator(db_session, grpc_context, caller):
    user = await _user(db_session)
    await _bind(await _link(user.id), grpc_context)
    caller(common_pb2.SOURCE_SERVICE_API)

    by_telegram = await AuthServicer().LookupOperator(
        auth_pb2.LookupOperatorRequest(telegram_user_id=TELEGRAM_ID), grpc_context
    )
    by_user = await AuthServicer().LookupOperator(
        auth_pb2.LookupOperatorRequest(user_id=user.id), grpc_context
    )

    assert by_telegram.found is True
    assert by_telegram.user_id == user.id
    assert by_telegram.username == "operator"
    assert list(by_telegram.roles) == ["operator"]
    assert by_telegram.active is True
    assert by_user.username == "operator"


async def test_lookup_of_unknown_subjects_finds_nothing(grpc_context, caller):
    caller(common_pb2.SOURCE_SERVICE_API)
    unknown = await AuthServicer().LookupOperator(
        auth_pb2.LookupOperatorRequest(telegram_user_id=OTHER_TELEGRAM_ID), grpc_context
    )
    malformed = await AuthServicer().LookupOperator(
        auth_pb2.LookupOperatorRequest(user_id="not-a-uuid"), grpc_context
    )
    assert unknown.found is False
    assert malformed.found is False


async def test_only_api_may_look_up(grpc_context, caller):
    with pytest.raises(FakeAbortError):
        await AuthServicer().LookupOperator(
            auth_pb2.LookupOperatorRequest(telegram_user_id=TELEGRAM_ID), grpc_context
        )


async def test_unbind_returns_the_previous_account(db_session, grpc_context, caller):
    user = await _user(db_session)
    await _bind(await _link(user.id), grpc_context)
    bindings = TelegramBindingRepository(db_session)

    previous = await bindings.unbind(user.id)
    await db_session.commit()

    assert previous == TELEGRAM_ID
    assert await bindings.get_for_user(user.id) is None
