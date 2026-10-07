from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TelegramLinkResponse(BaseModel):
    url: str
    expires_at: datetime


class TelegramStatus(BaseModel):
    linked: bool
    linked_at: datetime | None = None
