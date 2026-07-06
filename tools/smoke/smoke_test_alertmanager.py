from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")


TOKEN_FILE = Path("/run/secrets/webhook_token")
TARGET_URL = "http://notification:8000/webhooks/alertmanager"


def _payload(group_key: str) -> dict:
    return {
        "version": "4",
        "groupKey": group_key,
        "status": "firing",
        "receiver": "notification-service",
        "groupLabels": {"alertname": "SmokeAlert"},
        "commonLabels": {
            "alertname": "SmokeAlert",
            "severity": "warning",
            "service": "notification-smoke",
        },
        "commonAnnotations": {"summary": "smoke test firing"},
        "externalURL": "http://alertmanager:9093",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "SmokeAlert",
                    "severity": "warning",
                    "service": "notification-smoke",
                },
                "annotations": {"summary": "smoke test firing"},
                "startsAt": "2026-07-05T23:00:00Z",
                "endsAt": None,
                "generatorURL": "http://prometheus:9090",
                "fingerprint": "smoke-fp-001",
            }
        ],
    }


def _send(group_key: str) -> int:
    import requests

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        print("token file empty")
        return 1
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        TARGET_URL, json=_payload(group_key), headers=headers, timeout=5.0
    )
    print(f"status code: {resp.status_code}")
    print(f"group_key: {group_key}")
    if resp.status_code != 202:
        print(f"body: {resp.text}")
        print("send not accepted")
        return 1
    print("send accepted")
    return 0


async def _verify(group_key: str) -> int:
    from app.core.database import (
        close_mongodb_connection,
        connect_to_mongodb,
        get_collection,
    )
    from app.shared.config import settings

    await connect_to_mongodb()
    try:
        intents = get_collection(settings.DELIVERY_INTENT_COLLECTION)
        doc = await intents.find_one(
            {"source": "alertmanager", "source_ref": group_key}
        )
        if doc is None:
            print(f"no intent for group_key {group_key}")
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
    parser.add_argument("--group-key", default=f"smoke-{int(time.time())}")
    args = parser.parse_args()
    if args.send:
        return _send(args.group_key)
    if args.verify:
        return asyncio.run(_verify(args.group_key))
    parser.error("pass --send or --verify")


if __name__ == "__main__":
    sys.exit(main())
