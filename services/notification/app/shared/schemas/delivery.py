from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"
    BUFFERED = "buffered"


class Channel(str, Enum):
    TELEGRAM = "telegram"


class DeliverySource(str, Enum):
    ALERT = "alert"
    ALERTMANAGER = "alertmanager"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MongoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before", check_fields=False)
    @classmethod
    def _stringify_id(cls, v: object) -> object:
        return str(v) if v is not None else v


class DeliveryIntentCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: DeliverySource
    source_ref: str
    channel: Channel = Channel.TELEGRAM
    recipient: str
    payload: dict[str, Any]
    trace_carrier: dict[str, str] = Field(default_factory=dict)
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    requeue_count: int = 0
    attempt_started_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class DeliveryIntent(MongoModel):
    id: str = Field(alias="_id")
    source: DeliverySource
    source_ref: str
    channel: Channel
    recipient: str
    payload: dict[str, Any]
    trace_carrier: dict[str, str] = Field(default_factory=dict)
    status: DeliveryStatus
    attempts: int
    requeue_count: int = 0
    attempt_started_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class DeadLetterCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: DeliverySource
    source_ref: str
    channel: Channel = Channel.TELEGRAM
    recipient: str
    payload: dict[str, Any]
    trace_carrier: dict[str, str] = Field(default_factory=dict)
    attempts: int
    last_error: str | None = None
    intent_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class DeadLetter(MongoModel):
    id: str = Field(alias="_id")
    source: DeliverySource
    source_ref: str
    channel: Channel
    recipient: str
    payload: dict[str, Any]
    trace_carrier: dict[str, str] = Field(default_factory=dict)
    attempts: int
    last_error: str | None = None
    intent_id: str | None = None
    created_at: datetime
