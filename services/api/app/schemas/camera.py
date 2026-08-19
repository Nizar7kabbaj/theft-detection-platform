from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import MongoModel
from app.services.camera_health import HealthState


class CameraCreate(BaseModel):
    camera_id: str
    name: str
    location: str
    stream_url: str | None = None
    status: str = "active"


class CameraHealthView(BaseModel):
    state: HealthState = HealthState.UNKNOWN
    last_frame_at: datetime | None = None
    age_seconds: float | None = None


class CameraResponse(MongoModel):
    id: str = Field(alias="_id")
    camera_id: str
    name: str
    location: str
    stream_url: str | None = None
    status: str
    health: CameraHealthView = Field(default_factory=CameraHealthView)
    created_at: datetime
