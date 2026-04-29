"""
detections.py — Detection event endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from bson import ObjectId
from loguru import logger
from ...core.database import get_database
from ...models.schemas import DetectionCreate

router = APIRouter()


@router.post("/", response_model=dict)
async def create_detection(detection: DetectionCreate):
    """Save a detection event from the AI model."""
    db = get_database()
    detection_doc = {
        "session_id":  detection.session_id,
        "frame_index": detection.frame_index,
        "timestamp":   detection.timestamp,
        "camera_id":   detection.camera_id,
        "class_name":  detection.class_name,
        "confidence":  detection.confidence,
        "bbox":        detection.bbox.dict(),
        "created_at":  datetime.utcnow(),
    }
    result = await db.detections.insert_one(detection_doc)
    return {"id": str(result.inserted_id), "message": "Detection saved"}


@router.get("/", response_model=list)
async def get_detections(
    limit: int = Query(default=50, le=200),
    skip:  int = Query(default=0)
):
    """Get detection history with pagination."""
    db = get_database()
    detections = []
    cursor = db.detections.find().sort("created_at", -1).skip(skip).limit(limit)
    async for det in cursor:
        detections.append({
            "id":          str(det["_id"]),
            "session_id":  det["session_id"],
            "frame_index": det["frame_index"],
            "timestamp":   det["timestamp"],
            "camera_id":   det["camera_id"],
            "class_name":  det["class_name"],
            "confidence":  det["confidence"],
            "bbox":        det["bbox"],
        })
    return detections


@router.get("/session/{session_id}", response_model=list)
async def get_detections_by_session(session_id: int):
    """Get all detections from a specific session."""
    db = get_database()
    detections = []
    async for det in db.detections.find({"session_id": session_id}):
        detections.append({
            "id":          str(det["_id"]),
            "session_id":  det["session_id"],
            "frame_index": det["frame_index"],
            "timestamp":   det["timestamp"],
            "camera_id":   det["camera_id"],
            "class_name":  det["class_name"],
            "confidence":  det["confidence"],
            "bbox":        det["bbox"],
        })
    return detections


@router.delete("/{detection_id}", response_model=dict)
async def delete_detection(detection_id: str):
    """Delete a detection event."""
    db = get_database()
    result = await db.detections.delete_one({"_id": ObjectId(detection_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Detection not found")
    return {"message": "Detection deleted"}