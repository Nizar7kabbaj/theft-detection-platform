from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_int64(value: object) -> object:
    if isinstance(value, str):
        return int(value)
    return value


Int64 = Annotated[int, BeforeValidator(_coerce_int64)]


class Severity(str, Enum):
    SEVERITY_UNSPECIFIED = "SEVERITY_UNSPECIFIED"
    SEVERITY_INFO = "SEVERITY_INFO"
    SEVERITY_NOTICE = "SEVERITY_NOTICE"
    SEVERITY_WARNING = "SEVERITY_WARNING"
    SEVERITY_CRITICAL = "SEVERITY_CRITICAL"


class AlertType(str, Enum):
    ALERT_TYPE_UNSPECIFIED = "ALERT_TYPE_UNSPECIFIED"
    ALERT_TYPE_OBJECT_PROXIMITY = "ALERT_TYPE_OBJECT_PROXIMITY"
    ALERT_TYPE_BENDING = "ALERT_TYPE_BENDING"
    ALERT_TYPE_LOITERING = "ALERT_TYPE_LOITERING"


class Bbox(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x1: float
    y1: float
    x2: float
    y2: float


class Keypoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: float
    y: float
    confidence: float = Field(ge=0.0, le=1.0)


class Person(BaseModel):
    model_config = ConfigDict(extra="ignore")

    track_id: int = 0
    bbox: Bbox | None = None
    keypoints: list[Keypoint] = Field(default_factory=list)


class Object(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_name: str
    bbox: Bbox | None = None


class AlertMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alert_id: str
    session_id: Int64
    frame_index: int = 0
    occurred_at: datetime
    camera_id: str | None = None
    person: Person | None = None
    object: Object | None = None
    severity: Severity = Severity.SEVERITY_UNSPECIFIED
    alert_type: AlertType = AlertType.ALERT_TYPE_UNSPECIFIED
    snapshot_path: str | None = None
