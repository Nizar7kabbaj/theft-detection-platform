from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.roles import Role

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def _normalise_roles(values: list[Role]) -> list[Role]:
    if not values:
        raise ValueError("at least one role is required")
    seen: list[Role] = []
    for role in values:
        if role not in seen:
            seen.append(role)
    return seen


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    roles: list[str]
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None = None


class UserPage(BaseModel):
    items: list[UserSummary]
    total: int
    limit: int
    offset: int


class UserCounts(BaseModel):
    total: int
    active: int
    disabled: int
    live_sessions: int


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    roles: list[Role] = Field(min_length=1)

    _dedupe_roles = field_validator("roles")(_normalise_roles)


class UpdateRolesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[Role] = Field(min_length=1)

    _dedupe_roles = field_validator("roles")(_normalise_roles)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class SetActiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class RevokeSessionsResponse(BaseModel):
    revoked: int


class EraseAccountResponse(BaseModel):
    records_erased: int
    completed: bool
