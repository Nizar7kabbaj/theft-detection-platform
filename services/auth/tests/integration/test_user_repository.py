from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.repositories.user_repository import UserRepository

_HASH = "$argon2id$v=19$m=8192,t=1,p=1$c2FsdHNhbHQ$0000000000000000000000000000"


async def _create(session, username: str, roles: list[str] | None = None):
    repo = UserRepository(session)
    user = await repo.create(
        username=username,
        password_hash=_HASH,
        roles=roles if roles is not None else ["operator"],
    )
    await session.commit()
    return user


async def test_create_assigns_a_generated_uuid(db_session):
    user = await _create(db_session, "operator-one")

    assert uuid.UUID(user.id)


async def test_create_persists_username_and_hash(db_session):
    user = await _create(db_session, "operator-two")
    found = await UserRepository(db_session).get_by_username("operator-two")

    assert found is not None
    assert found.id == user.id
    assert found.password_hash == _HASH


async def test_create_stores_roles_as_array(db_session):
    user = await _create(db_session, "operator-three", roles=["admin", "viewer"])

    assert user.roles == ["admin", "viewer"]


async def test_empty_roles_default_to_empty_array(db_session):
    user = await _create(db_session, "operator-four", roles=[])

    assert user.roles == []


async def test_every_declared_role_is_accepted(db_session):
    roles = ["admin", "operator", "viewer", "ml_engineer", "compliance", "detector"]
    user = await _create(db_session, "operator-five", roles=roles)

    assert user.roles == roles


async def test_unknown_role_is_rejected(db_session):
    with pytest.raises(ValueError, match="not a valid Role"):
        await UserRepository(db_session).create(
            username="operator-six",
            password_hash=_HASH,
            roles=["superuser"],
        )


async def test_new_user_is_active_by_default(db_session):
    user = await _create(db_session, "operator-seven")

    assert user.is_active is True


async def test_timestamps_are_populated_and_aware(db_session):
    user = await _create(db_session, "operator-eight")

    assert user.created_at is not None
    assert user.created_at.tzinfo is not None
    assert user.updated_at is not None


async def test_get_by_username_returns_none_when_absent(db_session):
    assert await UserRepository(db_session).get_by_username("nobody") is None


async def test_get_by_username_is_case_sensitive(db_session):
    await _create(db_session, "operator-nine")

    assert await UserRepository(db_session).get_by_username("Operator-Nine") is None


async def test_get_by_id_round_trips(db_session):
    user = await _create(db_session, "operator-ten")
    found = await UserRepository(db_session).get_by_id(user.id)

    assert found is not None
    assert found.username == "operator-ten"


async def test_get_by_id_returns_none_for_unknown_uuid(db_session):
    assert await UserRepository(db_session).get_by_id(str(uuid.uuid4())) is None


async def test_duplicate_username_is_rejected(db_session):
    await _create(db_session, "operator-eleven")

    with pytest.raises(IntegrityError):
        await UserRepository(db_session).create(
            username="operator-eleven",
            password_hash=_HASH,
            roles=["viewer"],
        )


async def test_username_index_exists(db_session):
    result = await db_session.execute(
        text("select indexdef from pg_indexes where tablename = 'users'")
    )
    definitions = " ".join(row[0] for row in result.all())

    assert "username" in definitions
