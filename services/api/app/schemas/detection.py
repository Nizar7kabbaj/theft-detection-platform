from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Bbox, Keypoint, MongoModel


class DetectionCreate(BaseModel):
    session_id: int
    frame_index: int
    timestamp: str
    camera_id: str | None = "default"
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: Bbox
    keypoints: list[Keypoint] | None = None
    track_id: int = 0
    detection_present: bool = False


class DetectionResponse(MongoModel):
    id: str = Field(alias="_id")
    session_id: int
    frame_index: int
    timestamp: str
    camera_id: str
    class_name: str
    confidence: float
    bbox: Bbox
    keypoints: list[Keypoint] | None = None
    track_id: int
    detection_present: bool
    created_at: datetime
