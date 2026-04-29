"""
schemas.py — Pydantic models for request and response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Camera schemas ─────────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    name:       str
    location:   str
    stream_url: Optional[str] = None
    status:     str = "active"


class CameraResponse(BaseModel):
    id:         str
    name:       str
    location:   str
    stream_url: Optional[str] = None
    status:     str
    created_at: datetime


# ── Detection schemas ──────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class DetectionCreate(BaseModel):
    session_id:   int
    frame_index:  int
    timestamp:    str
    camera_id:    Optional[str] = "default"
    class_name:   str
    confidence:   float
    bbox:         BoundingBox


class DetectionResponse(BaseModel):
    id:           str
    session_id:   int
    frame_index:  int
    timestamp:    str
    camera_id:    str
    class_name:   str
    confidence:   float
    bbox:         BoundingBox


# ── Alert schemas ──────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    alert_id:    str
    session_id:  int
    frame_index: int
    timestamp:   str
    camera_id:   Optional[str] = "default"
    person:      dict
    object:      dict
    severity:    str
    snapshot_path: Optional[str] = None


class AlertResponse(BaseModel):
    id:          str
    alert_id:    str
    session_id:  int
    timestamp:   str
    camera_id:   str
    severity:    str
    object_name: str
    confidence:  float
    snapshot_url: Optional[str] = None


# ── Statistics schemas ─────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_alerts:      int
    total_detections:  int
    total_cameras:     int
    alerts_today:      int
    high_severity:     int
    medium_severity:   int
    top_objects:       List[dict]


# ── Auth schemas ───────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token:  str
    token_type:    str


class LoginRequest(BaseModel):
    username: str
    password: str