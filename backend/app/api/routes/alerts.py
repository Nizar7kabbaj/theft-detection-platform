"""
alerts.py — Alert management endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from bson import ObjectId
from loguru import logger
from ...core.database import get_database
from ...models.schemas import AlertCreate

router = APIRouter()


@router.post("/", response_model=dict)
async def create_alert(alert: AlertCreate):
    """Save an alert from the AI model."""
    db = get_database()
    alert_doc = {
        "alert_id":     alert.alert_id,
        "session_id":   alert.session_id,
        "frame_index":  alert.frame_index,
        "timestamp":    alert.timestamp,
        "camera_id":    alert.camera_id,
        "person":       alert.person,
        "object":       alert.object,
        "severity":     alert.severity,
        "snapshot_path": alert.snapshot_path,
        "created_at":   datetime.utcnow(),
        "acknowledged": False,
    }
    result = await db.alerts.insert_one(alert_doc)
    logger.warning(f"Alert saved: {alert.severity} — {alert.object.get('class_name')}")
    return {"id": str(result.inserted_id), "message": "Alert saved"}


@router.get("/", response_model=list)
async def get_alerts(
    limit:    int = Query(default=50, le=200),
    skip:     int = Query(default=0),
    severity: str = Query(default=None)
):
    """Get all alerts with optional severity filter."""
    db = get_database()
    query = {}
    if severity:
        query["severity"] = severity.upper()

    alerts = []
    cursor = db.alerts.find(query).sort("created_at", -1).skip(skip).limit(limit)
    async for alert in cursor:
        alerts.append({
            "id":           str(alert["_id"]),
            "alert_id":     alert["alert_id"],
            "session_id":   alert["session_id"],
            "timestamp":    alert["timestamp"],
            "camera_id":    alert["camera_id"],
            "severity":     alert["severity"],
            "object_name":  alert["object"].get("class_name"),
            "confidence":   alert["object"].get("confidence"),
            "acknowledged": alert["acknowledged"],
            "snapshot_path": alert.get("snapshot_path"),
        })
    return alerts


@router.patch("/{alert_id}/acknowledge", response_model=dict)
async def acknowledge_alert(alert_id: str):
    """Mark an alert as acknowledged."""
    db = get_database()
    result = await db.alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"acknowledged": True, "acknowledged_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert acknowledged"}


@router.delete("/{alert_id}", response_model=dict)
async def delete_alert(alert_id: str):
    """Delete an alert."""
    db = get_database()
    result = await db.alerts.delete_one({"_id": ObjectId(alert_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}