from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")


def _stale_payload(alert_id: str) -> dict:
    return {
        "alert_id": alert_id,
        "session_id": 1,
        "frame_index": 99,
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "camera_id": "cam-reconcile",
        "person": {
            "track_id": 3,
            "bbox": {"x1": 10.0, "y1": 20.0, "x2": 110.0, "y2": 220.0},
            "keypoints": [{"x": 15.0, "y": 25.0, "confidence": 0.9}],
        },
        "object": {
            "class_name": "backpack",
            "bbox": {"x1": 30.0, "y1": 40.0, "x2": 90.0, "y2": 140.0},
        },
        "severity": "SEVERITY_WARNING",
        "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
    }


async def _insert(alert_id: str) -> int:
    from app.core.database import (
        close_mongodb_connection,
        connect_to_mongodb,
        get_collection,
    )
    from app.shared.config import settings

    await connect_to_mongodb()
    try:
        intents = get_collection(settings.DELIVERY_INTENT_COLLECTION)
        stale = datetime.now(timezone.utc) - timedelta(minutes=10)
        recipient = settings.TELEGRAM_CHAT_ID or "unconfigured"
        doc = {
            "source": "alert",
            "source_ref": alert_id,
            "channel": "telegram",
            "recipient": recipient,
            "payload": _stale_payload(alert_id),
            "trace_carrier": {},
            "status": "sending",
            "attempts": 0,
            "requeue_count": 0,
            "attempt_started_at": stale,
            "last_error": None,
            "created_at": stale,
            "updated_at": stale,
        }
        result = await intents.insert_one(doc)
        print(f"inserted intent_id={result.inserted_id}")
        print(f"alert_id={alert_id}")
        print(f"stale_since={stale.isoformat()}")
        print("waiting for reconciler beat tick (up to 60s)")
        return 0
    finally:
        await close_mongodb_connection()


async def _verify(alert_id: str) -> int:
    from app.core.database import (
        close_mongodb_connection,
        connect_to_mongodb,
        get_collection,
    )
    from app.shared.config import settings

    await connect_to_mongodb()
    try:
        intents = get_collection(settings.DELIVERY_INTENT_COLLECTION)
        doc = await intents.find_one({"source": "alert", "source_ref": alert_id})
        if doc is None:
            print(f"no intent for alert_id {alert_id}")
            return 1
        print(f"status: {doc['status']}")
        print(f"attempts: {doc['attempts']}")
        print(f"requeue_count: {doc['requeue_count']}")
        print(f"attempt_started_at: {doc['attempt_started_at']}")
        n = await intents.count_documents({"source": "alert", "source_ref": alert_id})
        print(f"row count: {n}")
        ok = (
            doc["status"] == "sent"
            and doc["attempts"] == 1
            and doc["requeue_count"] == 1
            and doc["attempt_started_at"] is None
            and n == 1
        )
        print("reconcile ok" if ok else "reconcile mismatch")
        return 0 if ok else 1
    finally:
        await close_mongodb_connection()


async def _cleanup(alert_id: str) -> int:
    from app.core.database import (
        close_mongodb_connection,
        connect_to_mongodb,
        get_collection,
    )
    from app.shared.config import settings

    await connect_to_mongodb()
    try:
        intents = get_collection(settings.DELIVERY_INTENT_COLLECTION)
        result = await intents.delete_many(
            {"source": "alert", "source_ref": alert_id}
        )
        print(f"deleted {result.deleted_count}")
        return 0
    finally:
        await close_mongodb_connection()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--insert", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--alert-id", default=f"reconcile-{int(time.time())}")
    args = parser.parse_args()
    if args.insert:
        return asyncio.run(_insert(args.alert_id))
    if args.verify:
        return asyncio.run(_verify(args.alert_id))
    if args.cleanup:
        return asyncio.run(_cleanup(args.alert_id))
    parser.error("pass --insert, --verify, or --cleanup")


if __name__ == "__main__":
    sys.exit(main())
