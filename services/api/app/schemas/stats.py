from pydantic import BaseModel


class TopObject(BaseModel):
    object: str | None
    count: int


class StatsResponse(BaseModel):
    total_alerts: int
    total_detections: int
    total_cameras: int
    alerts_today: int
    high_severity: int
    medium_severity: int
    top_objects: list[TopObject]
