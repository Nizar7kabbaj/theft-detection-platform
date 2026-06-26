from pydantic import BaseModel, Field

from app.schemas.common import MongoModel


class AlertCreate(BaseModel):
    alert_id: str
    session_id: int
    frame_index: int
    timestamp: str
    camera_id: str | None = "default"
    person: dict
    object: dict | None = None
    severity: str
    snapshot_path: str | None = None
    alert_type: str | None = "object_proximity"
    keypoints: list[dict] | None = None
    torso_angle: float | None = None


class AlertResponse(MongoModel):
    id: str = Field(alias="_id")
    alert_id: str
    session_id: int
    timestamp: str
    camera_id: str
    severity: str
    object_name: str
    confidence: float | None = None
    snapshot_url: str | None = None
    alert_type: str | None = None
