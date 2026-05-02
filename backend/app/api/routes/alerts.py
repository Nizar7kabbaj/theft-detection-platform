"""
alerts.py — Alert management endpoints
Updated TDP-32: handle bend alerts (no object field)
Updated TDP-35: send Telegram notification on new alert (background task)
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from datetime import datetime
from bson import ObjectId
from loguru import logger
from ...core.database import get_database
from ...models.schemas import AlertCreate
from ...services.telegram_service import send_message as send_telegram

router = APIRouter()


def _build_telegram_text(alert: AlertCreate) -> str:
    """Build a human-readable Telegram message from an alert."""
    if alert.alert_type == "bending":
        what = "Person bending (possible concealment)"
    elif alert.object:
        what = f"Person near {alert.object.get('class_name', 'object')}"
    else:
        what = alert.alert_type or "Suspicious activity"

    angle_line = ""
    if alert.torso_angle is not None:
        angle_line = f"\n📐 Torso angle: <b>{alert.torso_angle:.1f}°</b>"

    return (
        f"🚨 <b>TheftGuard Alert — {alert.severity}</b>\n"
        f"📌 {what}\n"
        f"📷 Camera: <code>{alert.camera_id}</code>\n"
        f"🕒 {alert.timestamp}"
        f"{angle_line}"
    )


@router.post("/", response_model=dict)
async def create_alert(alert: AlertCreate, background_tasks: BackgroundTasks):
    """Save an alert from the AI model and notify Telegram in the background."""
    db = get_database()
    alert_doc = {
        "alert_id":      alert.alert_id,
        "session_id":    alert.session_id,
        "frame_index":   alert.frame_index,
        "timestamp":     alert.timestamp,
        "camera_id":     alert.camera_id,
        "person":        alert.person,
        "object":        alert.object,
        "severity":      alert.severity,
        "snapshot_path": alert.snapshot_path,
        "alert_type":    alert.alert_type,
        "keypoints":     alert.keypoints,
        "torso_angle":   alert.torso_angle,
        "created_at":    datetime.utcnow(),
        "acknowledged":  False,
    }
    result = await db.alerts.insert_one(alert_doc)

    label = alert.object.get("class_name") if alert.object else alert.alert_type
    logger.warning(f"Alert saved: {alert.severity} — {label}")

    # TDP-35: notify Telegram AFTER response is sent (non-blocking, fail-safe)
    background_tasks.add_task(send_telegram, _build_telegram_text(alert))

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
        obj = alert.get("object") or {}
        alert_type = alert.get("alert_type", "object_proximity")

        if obj:
            object_name = obj.get("class_name", "unknown")
            confidence  = obj.get("confidence")
        else:
            object_name = "person bending" if alert_type == "bending" else alert_type
            confidence  = None

        alerts.append({
            "id":            str(alert["_id"]),
            "alert_id":      alert["alert_id"],
            "session_id":    alert["session_id"],
            "timestamp":     alert["timestamp"],
            "camera_id":     alert["camera_id"],
            "severity":      alert["severity"],
            "object_name":   object_name,
            "confidence":    confidence,
            "alert_type":    alert_type,
            "acknowledged":  alert["acknowledged"],
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