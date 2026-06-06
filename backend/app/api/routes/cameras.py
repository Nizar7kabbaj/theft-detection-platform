import logging
from fastapi import APIRouter, HTTPException
from datetime import datetime
from bson import ObjectId
from ...core.database import get_database
from ...models.schemas import CameraCreate, CameraResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=dict)
async def create_camera(camera: CameraCreate):
    db = get_database()
    camera_doc = {
        "name":       camera.name,
        "location":   camera.location,
        "stream_url": camera.stream_url,
        "status":     camera.status,
        "created_at": datetime.utcnow(),
    }
    result = await db.cameras.insert_one(camera_doc)
    logger.info("camera created", extra={"camera_name": camera.name})
    return {"id": str(result.inserted_id), "message": "Camera created successfully"}


@router.get("/", response_model=list)
async def get_cameras():
    db = get_database()
    cameras = []
    async for camera in db.cameras.find():
        cameras.append({
            "id":         str(camera["_id"]),
            "name":       camera["name"],
            "location":   camera["location"],
            "stream_url": camera.get("stream_url"),
            "status":     camera["status"],
            "created_at": camera["created_at"].isoformat(),
        })
    return cameras


@router.get("/{camera_id}", response_model=dict)
async def get_camera(camera_id: str):
    db = get_database()
    camera = await db.cameras.find_one({"_id": ObjectId(camera_id)})
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {
        "id":         str(camera["_id"]),
        "name":       camera["name"],
        "location":   camera["location"],
        "stream_url": camera.get("stream_url"),
        "status":     camera["status"],
        "created_at": camera["created_at"].isoformat(),
    }


@router.delete("/{camera_id}", response_model=dict)
async def delete_camera(camera_id: str):
    db = get_database()
    result = await db.cameras.delete_one({"_id": ObjectId(camera_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"message": "Camera deleted successfully"}
