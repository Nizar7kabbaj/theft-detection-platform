from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class BucketUnit(str, Enum):
    HOUR = "hour"
    DAY = "day"


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


class AlertBucket(BaseModel):
    bucket: datetime
    critical: int
    warning: int
    notice: int
    info: int
    unspecified: int
    total: int


class DecisionBucket(BaseModel):
    bucket: datetime
    confirmed: int
    dismissed: int
    unsure: int
    total: int


class StatsTimeseriesResponse(BaseModel):
    start: datetime
    end: datetime
    unit: BucketUnit
    alerts: list[AlertBucket]
    decisions: list[DecisionBucket]
