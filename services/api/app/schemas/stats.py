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


class EdgeStatsResponse(BaseModel):
    average_fps: float | None
    latency_ms: float | None
    gpu_temperature_c: int | None
    gpu_name: str | None
    reporting_cameras: int
    total_cameras: int


class ServiceMemory(BaseModel):
    camera: int | None
    gate: int | None
    inference: int | None
    notification: int | None


class SystemStatsResponse(BaseModel):
    cpu_percent: float | None
    memory_percent: float | None
    network_bytes_per_second: float | None
    gpu_percent: float | None
    gpu_temperature_c: int | None
    cpu_temperature_c: int | None
    service_memory_bytes: ServiceMemory


class SystemHistoryResponse(BaseModel):
    cpu: list[float]
    gpu: list[float]
    memory: list[float]
    network: list[float]
    cpu_temperature: list[float]
    gpu_temperature: list[float]
