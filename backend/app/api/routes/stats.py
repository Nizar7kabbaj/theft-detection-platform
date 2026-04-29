"""
stats.py — Dashboard statistics endpoints
"""
from fastapi import APIRouter
from datetime import datetime, timedelta
from ...core.database import get_database

router = APIRouter()


@router.get("/", response_model=dict)
async def get_stats():
    """Get dashboard statistics."""
    db = get_database()

    # Today's date range
    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Run all counts in parallel
    total_alerts      = await db.alerts.count_documents({})
    total_detections  = await db.detections.count_documents({})
    total_cameras     = await db.cameras.count_documents({})
    alerts_today      = await db.alerts.count_documents(
        {"created_at": {"$gte": today_start}}
    )
    high_severity     = await db.alerts.count_documents({"severity": "HIGH"})
    medium_severity   = await db.alerts.count_documents({"severity": "MEDIUM"})

    # Top detected objects
    pipeline = [
        {"$group": {"_id": "$object.class_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_objects = []
    async for doc in db.alerts.aggregate(pipeline):
        top_objects.append({
            "object": doc["_id"],
            "count":  doc["count"]
        })

    return {
        "total_alerts":     total_alerts,
        "total_detections": total_detections,
        "total_cameras":    total_cameras,
        "alerts_today":     alerts_today,
        "high_severity":    high_severity,
        "medium_severity":  medium_severity,
        "top_objects":      top_objects,
    }


@router.get("/recent", response_model=list)
async def get_recent_alerts():
    """Get last 10 alerts for dashboard feed."""
    db = get_database()
    alerts = []
    cursor = db.alerts.find().sort("created_at", -1).limit(10)
    async for alert in cursor:
        alerts.append({
            "id":          str(alert["_id"]),
            "timestamp":   alert["timestamp"],
            "severity":    alert["severity"],
            "object_name": alert["object"].get("class_name"),
            "camera_id":   alert["camera_id"],
        })
    return alerts