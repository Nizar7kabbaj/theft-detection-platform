from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.services.camera_reconcile import TRANSITION_LUA
from app.services.policy_sync import PUBLISH_NEWER_LUA

ROOT = Path(__file__).resolve().parents[2]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6390
STATE_TTL = 30
EXPECTED_EVENTS = 3
HELD_VERSION = 5
DRAIN_SECONDS = 1.0
UNCHECKED = "unused"
RESULTS: list[bool] = []


def check(name: str, ok: bool) -> None:
    RESULTS.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")


def acl_rules(path: Path, user: str) -> list[str]:
    for line in path.read_text().splitlines():
        tokens = line.split()
        if tokens[:2] == ["user", user]:
            return [t for t in tokens[2:] if not t.startswith((">", "#"))] + ["nopass"]
    raise SystemExit(f"user {user} missing from {path.name}")


def connect(user: str | None = None) -> Redis:
    if user is None:
        return Redis(host="127.0.0.1", port=PORT)
    return Redis(host="127.0.0.1", port=PORT, username=user, password=UNCHECKED)


async def drain(pubsub) -> int:
    count = 0
    deadline = time.monotonic() + DRAIN_SECONDS
    while time.monotonic() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if message is not None:
            count += 1
    return count


async def camera_checks(admin: Redis) -> None:
    api = connect("api")
    pubsub = admin.pubsub()
    await pubsub.subscribe("cameras:health")
    script = api.register_script(TRANSITION_LUA)
    key = "health:camera:cam-1"

    async def run(state: str, observed: int, target: str = key) -> int:
        payload = json.dumps({"state": state})
        return await script(
            keys=[target], args=[state, observed, STATE_TTL, "cameras:health", payload]
        )

    check("camera first state publishes", await run("online", 1000) == 1)
    check("camera same state stays quiet", await run("online", 2000) == 0)
    check("camera older observation ignored", await run("offline", 1500) == 0)
    check("camera newer change publishes", await run("degraded", 3000) == 1)
    ttl = await admin.ttl(key)
    check("camera state key keeps a ttl", 0 < ttl <= STATE_TTL)
    await admin.set(key, "unparsable")
    check("camera unparsable state republishes", await run("online", 4000) == 1)
    check("camera channel saw exactly 3 events", await drain(pubsub) == EXPECTED_EVENTS)
    await run("online", 5000, target="cache:other")
    check("api user writes inside its key patterns", await admin.exists("cache:other") == 1)
    refused = False
    try:
        await run("online", 6000, target="secret:x")
    except ResponseError as exc:
        print(f"     refusal: {exc}")
        refused = True
    check(
        "api user refused outside its key patterns",
        refused and await admin.exists("secret:x") == 0,
    )
    await pubsub.aclose()
    await api.aclose()


async def policy_checks(admin: Redis) -> None:
    stream = connect("api-health")
    pubsub = admin.pubsub()
    await pubsub.subscribe("policy:detection")
    script = stream.register_script(PUBLISH_NEWER_LUA)
    key = "policy:detection:current"

    async def run(version: int) -> int:
        body = json.dumps({"version": version})
        return await script(keys=[key], args=[version, body, "policy:detection"])

    check("policy first version publishes", await run(HELD_VERSION) == 1)
    check("policy same version stays quiet", await run(HELD_VERSION) == 0)
    check("policy older version refused", await run(HELD_VERSION - 1) == 0)
    stored = json.loads(await admin.get(key))
    check("policy older version left store untouched", stored["version"] == HELD_VERSION)
    check("policy newer version publishes", await run(HELD_VERSION + 1) == 1)
    await admin.set(key, "not json")
    check("policy unparsable store is replaced", await run(HELD_VERSION + 2) == 1)
    check("policy channel saw exactly 3 events", await drain(pubsub) == EXPECTED_EVENTS)
    await pubsub.aclose()
    await stream.aclose()


async def main() -> int:
    admin = connect()
    await admin.flushall()
    main_acl = acl_rules(ROOT / "config/redis/redis.acl", "api")
    stream_acl = acl_rules(ROOT / "config/redis/redis-stream.acl", "api-health")
    await admin.execute_command("ACL", "SETUSER", "api", "reset", *main_acl)
    await admin.execute_command("ACL", "SETUSER", "api-health", "reset", *stream_acl)
    await camera_checks(admin)
    await policy_checks(admin)
    await admin.aclose()
    print(f"===== lua {sum(RESULTS)}/{len(RESULTS)} passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
