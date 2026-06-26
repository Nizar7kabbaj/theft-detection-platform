from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import MongoModel


class CameraCreate(BaseModel):
    name: str
    location: str
    stream_url: str | None = None
    status: str = "active"


class CameraResponse(MongoModel):
    id: str = Field(alias="_id")
    name: str
    location: str
    stream_url: str | None = None
    status: str
    created_at: datetime
