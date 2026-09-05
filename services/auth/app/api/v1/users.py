from __future__ import annotations

from typing import Annotated

import grpc
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Actor, require_admin
from app.core.config import get_settings
from app.core.csrf import csrf_protect
from app.core.database import get_sessionmaker
from app.core.redis import revoke_sid
from app.core.roles import Role
from app.core.security import hash_password
from app.db.models.user import User
from app.repositories.audit_outbox_repository import AuditOutboxRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.users import (
    CreateUserRequest,
    EraseAccountResponse,
    ResetPasswordRequest,
    RevokeSessionsResponse,
    SetActiveRequest,
    UpdateRolesRequest,
    UserCounts,
    UserPage,
    UserSummary,
)
from app.server.grpc_gen import audit_pb2 as pb
from app.services import audit_service as audit_events

router = APIRouter(
    prefix="/auth/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)

_USER_NOT_FOUND = "user not found"
_USERNAME_TAKEN = "username already exists"
_SELF_DISABLE = "an admin cannot disable their own account"
_SELF_DEMOTE = "an admin cannot remove their own admin role"
_LAST_ADMIN = "the last active admin cannot be disabled or demoted"
_SELF_DELETE = "an admin cannot delete their own account"
_ERASURE_UNAVAILABLE = "the audit service is unreachable, nothing was deleted"

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


async def _load(db: AsyncSession, user_id: str) -> User:
    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND)
    return user


async def _guard_last_admin(db: AsyncSession, target: User) -> None:
    if Role.ADMIN not in target.roles or not target.is_active:
        return
    remaining = await UserRepository(db).count_filtered(role=Role.ADMIN, is_active=True)
    if remaining <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_LAST_ADMIN)


async def _drop_sessions(db: AsyncSession, user_id: str, actor: Actor) -> list[str]:
    sessions = SessionRepository(db)
    live = await sessions.live_ids_for_user(user_id)
    if not live:
        return []
    await sessions.revoke_all_for_user(user_id)
    outbox = AuditOutboxRepository(db)
    for session_id in live:
        event = audit_events.admin_session_revoked(
            actor_user_id=actor.user_id,
            session_id=session_id,
        )
        await outbox.enqueue(event.event_id, event.event_bytes, event.occurred_at)
    return live


async def _push_revocations(session_ids: list[str]) -> None:
    ttl = get_settings().access_token_ttl_seconds
    for session_id in session_ids:
        await revoke_sid(session_id, ttl)


@router.get("/counts", response_model=UserCounts)
async def user_counts() -> UserCounts:
    factory = get_sessionmaker()
    async with factory() as db:
        active, disabled = await UserRepository(db).count_by_active()
        live = await SessionRepository(db).count_live()
    return UserCounts(
        total=active + disabled,
        active=active,
        disabled=disabled,
        live_sessions=live,
    )


@router.get("", response_model=UserPage)
async def list_users(
    search: Annotated[str | None, Query(max_length=50)] = None,
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    factory = get_sessionmaker()
    async with factory() as db:
        users = UserRepository(db)
        rows = await users.list_users(
            search=search,
            role=role,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
        total = await users.count_filtered(search=search, role=role, is_active=is_active)
        seen = await SessionRepository(db).last_used_by_user([row.id for row in rows])
    items = [
        UserSummary(
            id=row.id,
            username=row.username,
            roles=list(row.roles),
            is_active=row.is_active,
            created_at=row.created_at,
            last_active_at=seen.get(row.id),
        )
        for row in rows
    ]
    return UserPage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> UserSummary:
    password_hash = hash_password(payload.password)
    factory = get_sessionmaker()
    async with factory() as db:
        users = UserRepository(db)
        if await users.get_by_username(payload.username) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_USERNAME_TAKEN)
        created = await users.create(
            username=payload.username,
            password_hash=password_hash,
            roles=[str(role) for role in payload.roles],
        )
        event = audit_events.admin_user_created(
            actor_user_id=actor.user_id,
            target_user_id=created.id,
        )
        await AuditOutboxRepository(db).enqueue(
            event.event_id, event.event_bytes, event.occurred_at
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_USERNAME_TAKEN
            ) from exc
        return UserSummary(
            id=created.id,
            username=created.username,
            roles=list(created.roles),
            is_active=created.is_active,
            created_at=created.created_at,
            last_active_at=None,
        )


@router.get("/{user_id}", response_model=UserSummary)
async def get_user(user_id: str) -> UserSummary:
    factory = get_sessionmaker()
    async with factory() as db:
        user = await _load(db, user_id)
        seen = await SessionRepository(db).last_used_by_user([user.id])
    return UserSummary(
        id=user.id,
        username=user.username,
        roles=list(user.roles),
        is_active=user.is_active,
        created_at=user.created_at,
        last_active_at=seen.get(user.id),
    )


@router.put("/{user_id}/roles", response_model=UserSummary)
async def update_roles(
    user_id: str,
    payload: UpdateRolesRequest,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> UserSummary:
    requested = [str(role) for role in payload.roles]
    factory = get_sessionmaker()
    async with factory() as db:
        user = await _load(db, user_id)
        before = set(user.roles)
        after = set(requested)
        if before == after:
            seen = await SessionRepository(db).last_used_by_user([user.id])
            return UserSummary(
                id=user.id,
                username=user.username,
                roles=list(user.roles),
                is_active=user.is_active,
                created_at=user.created_at,
                last_active_at=seen.get(user.id),
            )
        losing_admin = Role.ADMIN in before and Role.ADMIN not in after
        if losing_admin and user.id == actor.user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_SELF_DEMOTE)
        if losing_admin:
            await _guard_last_admin(db, user)
        updated = await UserRepository(db).set_roles(user, requested)
        outbox = AuditOutboxRepository(db)
        if after - before:
            granted = audit_events.admin_roles_granted(
                actor_user_id=actor.user_id,
                target_user_id=updated.id,
            )
            await outbox.enqueue(granted.event_id, granted.event_bytes, granted.occurred_at)
        if before - after:
            revoked = audit_events.admin_roles_revoked(
                actor_user_id=actor.user_id,
                target_user_id=updated.id,
            )
            await outbox.enqueue(revoked.event_id, revoked.event_bytes, revoked.occurred_at)
        await db.commit()
        seen = await SessionRepository(db).last_used_by_user([updated.id])
        return UserSummary(
            id=updated.id,
            username=updated.username,
            roles=list(updated.roles),
            is_active=updated.is_active,
            created_at=updated.created_at,
            last_active_at=seen.get(updated.id),
        )


@router.put("/{user_id}/active", response_model=UserSummary)
async def set_active(
    user_id: str,
    payload: SetActiveRequest,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> UserSummary:
    dropped: list[str] = []
    factory = get_sessionmaker()
    async with factory() as db:
        user = await _load(db, user_id)
        if user.is_active == payload.is_active:
            seen = await SessionRepository(db).last_used_by_user([user.id])
            return UserSummary(
                id=user.id,
                username=user.username,
                roles=list(user.roles),
                is_active=user.is_active,
                created_at=user.created_at,
                last_active_at=seen.get(user.id),
            )
        if not payload.is_active:
            if user.id == actor.user_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_SELF_DISABLE)
            await _guard_last_admin(db, user)
        updated = await UserRepository(db).set_active(user, payload.is_active)
        if not payload.is_active:
            dropped = await _drop_sessions(db, updated.id, actor)
        event = (
            audit_events.admin_user_enabled(
                actor_user_id=actor.user_id,
                target_user_id=updated.id,
            )
            if payload.is_active
            else audit_events.admin_user_disabled(
                actor_user_id=actor.user_id,
                target_user_id=updated.id,
            )
        )
        await AuditOutboxRepository(db).enqueue(
            event.event_id, event.event_bytes, event.occurred_at
        )
        await db.commit()
        seen = await SessionRepository(db).last_used_by_user([updated.id])
        summary = UserSummary(
            id=updated.id,
            username=updated.username,
            roles=list(updated.roles),
            is_active=updated.is_active,
            created_at=updated.created_at,
            last_active_at=seen.get(updated.id),
        )
    await _push_revocations(dropped)
    return summary


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> Response:
    password_hash = hash_password(payload.password)
    factory = get_sessionmaker()
    async with factory() as db:
        user = await _load(db, user_id)
        await UserRepository(db).set_password_hash(user, password_hash)
        dropped = await _drop_sessions(db, user.id, actor)
        event = audit_events.admin_password_reset(
            actor_user_id=actor.user_id,
            target_user_id=user.id,
        )
        await AuditOutboxRepository(db).enqueue(
            event.event_id, event.event_bytes, event.occurred_at
        )
        await db.commit()
    await _push_revocations(dropped)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/sessions/revoke", response_model=RevokeSessionsResponse)
async def revoke_sessions(
    user_id: str,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> RevokeSessionsResponse:
    factory = get_sessionmaker()
    async with factory() as db:
        user = await _load(db, user_id)
        dropped = await _drop_sessions(db, user.id, actor)
        await db.commit()
    await _push_revocations(dropped)
    return RevokeSessionsResponse(revoked=len(dropped))


@router.delete("/{user_id}", response_model=EraseAccountResponse)
async def delete_user(
    user_id: str,
    actor: Annotated[Actor, Depends(require_admin)],
    _: Annotated[None, Depends(csrf_protect)],
) -> EraseAccountResponse:
    factory = get_sessionmaker()
    async with factory() as db:
        target = await _load(db, user_id)
        if target.id == actor.user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_SELF_DELETE)
        await _guard_last_admin(db, target)
        live = await SessionRepository(db).live_ids_for_user(target.id)
        await db.rollback()

    try:
        erased, completed = await audit_events.erase_subject(
            subject_id=user_id,
            requested_by=actor.user_id,
            reason=pb.ERASURE_REASON_ACCOUNT_DELETED,
        )
    except grpc.aio.AioRpcError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_ERASURE_UNAVAILABLE,
        ) from exc

    async with factory() as db:
        target = await _load(db, user_id)
        await SessionRepository(db).delete_for_user(target.id)
        await UserRepository(db).delete(target)
        event = audit_events.data_subject_erasure(
            actor_user_id=actor.user_id,
            subject_id=user_id,
            records_erased=erased,
            completed=completed,
        )
        if event is not None:
            await AuditOutboxRepository(db).enqueue(
                event.event_id, event.event_bytes, event.occurred_at
            )
        await db.commit()

    await _push_revocations(live)
    return EraseAccountResponse(records_erased=erased, completed=completed)
