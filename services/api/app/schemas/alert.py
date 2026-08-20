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
    ALERT_TYPE_CONCEALMENT = "ALERT_TYPE_CONCEALMENT"
    ALERT_TYPE_LOITERING = "ALERT_TYPE_LOITERING"


class Decision(str, Enum):
    DECISION_UNSPECIFIED = "DECISION_UNSPECIFIED"
    DECISION_CONFIRMED = "DECISION_CONFIRMED"
    DECISION_DISMISSED = "DECISION_DISMISSED"
    DECISION_UNSURE = "DECISION_UNSURE"


class AlertSort(str, Enum):
    CREATED_AT = "created_at"
    DECIDED_AT = "decided_at"


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


class Concealment(BaseModel):
    object_track_id: int
    object_class: str
    last_seen_frame: int
    missing_frames: int
    person_track_id: int
    wrist_index: int
    wrist_x: float
    wrist_y: float
    grab_distance: float


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
    frame_width: int | None = None
    frame_height: int | None = None
    concealment: Concealment | None = None
    classifier_score: float | None = None
    classifier_state: str | None = None


class DecisionUpdate(BaseModel):
    decision: Decision


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
    decision: Decision = Decision.DECISION_UNSPECIFIED
    decided_at: datetime | None = None
    decided_by: str | None = None


class AlertDetail(MongoModel):
    id: str = Field(alias="_id")
    alert_id: str
    session_id: int
    frame_index: int
    occurred_at: datetime
    created_at: datetime
    camera_id: str
    severity: Severity
    alert_type: AlertType | None = None
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    decision: Decision = Decision.DECISION_UNSPECIFIED
    decided_at: datetime | None = None
    decided_by: str | None = None
    person: Person | None = None
    object: Object | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    concealment: Concealment | None = None
    classifier_score: float | None = None
    classifier_state: str | None = None
    snapshot_url: str | None = None


class AlertPage(BaseModel):
    items: list[AlertResponse]
    next_cursor: str | None = None
