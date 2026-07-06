from __future__ import annotations

import argparse
import asyncio
import sys
import time

sys.path.insert(0, "/app")


def _send(alert_id: str) -> int:
    import grpc
    from google.protobuf.timestamp_pb2 import Timestamp

    from app.server.grpc_gen import alert_pb2, alert_pb2_grpc, common_pb2

    occurred = Timestamp()
    occurred.GetCurrentTime()

    alert = alert_pb2.Alert(
        alert_id=alert_id,
        session_id=1,
        frame_index=42,
        occurred_at=occurred,
        camera_id="cam-smoke",
        person=common_pb2.Person(
            track_id=7,
            bbox=common_pb2.Bbox(x1=10.0, y1=20.0, x2=110.0, y2=220.0),
            keypoints=[common_pb2.Keypoint(x=15.0, y=25.0, confidence=0.9)],
        ),
        object=common_pb2.Object(
            class_name="handbag",
            bbox=common_pb2.Bbox(x1=30.0, y1=40.0, x2=90.0, y2=140.0),
        ),
        severity=common_pb2.SEVERITY_WARNING,
        alert_type=common_pb2.ALERT_TYPE_OBJECT_PROXIMITY,
    )

    channel = grpc.insecure_channel("notification-service:50052")
    stub = alert_pb2_grpc.AlertServiceStub(channel)
    reply = stub.SendAlert(alert, timeout=5.0)
    channel.close()

    status_name = alert_pb2.Status.Name(reply.status)
    print(f"reply status: {status_name}")
    print(f"alert_id: {alert_id}")
    if reply.status != alert_pb2.STATUS_ACCEPTED:
        print("send not accepted")
        return 1
    print("send accepted")
    return 0


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
        print(f"attempt_started_at: {doc['attempt_started_at']}")
        print(f"trace_carrier keys: {sorted(doc.get('trace_carrier', {}))}")
        ok = (
            doc["status"] == "sent"
            and doc["attempts"] == 1
            and doc["attempt_started_at"] is None
            and bool(doc.get("trace_carrier"))
        )
        print("lifecycle ok" if ok else "lifecycle mismatch")
        return 0 if ok else 1
    finally:
        await close_mongodb_connection()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--alert-id", default=f"smoke-{int(time.time())}")
    args = parser.parse_args()

    if args.send:
        return _send(args.alert_id)
    if args.verify:
        return asyncio.run(_verify(args.alert_id))
    parser.error("pass --send or --verify")


if __name__ == "__main__":
    sys.exit(main())
