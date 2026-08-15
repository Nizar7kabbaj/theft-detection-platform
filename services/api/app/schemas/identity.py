from pydantic import BaseModel

from app.core.permissions import Permission


class CurrentUser(BaseModel):
    user_id: str
    username: str
    roles: frozenset[str]
    session_id: str


class IdentityResponse(BaseModel):
    user_id: str
    username: str
    roles: list[str]
    permissions: list[Permission]
