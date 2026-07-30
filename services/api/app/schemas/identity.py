from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: str
    username: str
    roles: frozenset[str]
    session_id: str
