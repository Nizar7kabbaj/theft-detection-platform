from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DeliveryState(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"
    BUFFERED = "buffered"


class DeliveryRecord(BaseModel):
    channel: str
    recipient: str
    state: DeliveryState
    attempts: int
    requeue_count: int
    last_error_class: str | None = None
    created_at: datetime
    updated_at: datetime


class DeliveryStatusView(BaseModel):
    known: bool
    records: list[DeliveryRecord]


class DeliverySummary(BaseModel):
    known: bool
    state: DeliveryState
    attempts: int
