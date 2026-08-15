from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import MongoModel


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
    x1: float
    y1: float
    x2: float
    y2: float


class Keypoint(BaseModel):
    x: float
    y: float
    confidence: float = Field(ge=0.0, le=1.0)


class Person(BaseModel):
    track_id: int = 0
    bbox: Bbox | None = None
    keypoints: list[Keypoint] = Field(default_factory=list)


class Object(BaseModel):
    class_name: str
    bbox: Bbox | None = None


class AlertCreate(BaseModel):
    alert_id: str
    session_id: int
    frame_index: int
    occurred_at: datetime
    camera_id: str | None = "default"
    person: Person | None = None
    object: Object | None = None
    severity: Severity
    snapshot_path: str | None = None
    alert_type: AlertType = AlertType.ALERT_TYPE_OBJECT_PROXIMITY


class AlertResponse(MongoModel):
    id: str = Field(alias="_id")
    alert_id: str
    session_id: int
    occurred_at: datetime
    created_at: datetime
    camera_id: str
    severity: Severity
    object_name: str
    confidence: float | None = None
    snapshot_url: str | None = None
    alert_type: AlertType | None = None
    acknowledged: bool = False
    acknowledged_at: datetime | None = None


class AlertPage(BaseModel):
    items: list[AlertResponse]
    next_cursor: str | None = None
