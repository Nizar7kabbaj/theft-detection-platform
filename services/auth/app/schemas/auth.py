from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    token_type: str = "Bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    revoked: bool


class MessageResponse(BaseModel):
    detail: str
