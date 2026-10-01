import asyncio
import json
import ssl
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

ROOT = Path(__file__).resolve().parents[2]
CA = ROOT / "config" / "traefik" / "certs" / "ca.crt"
SECRETS = {
    "admin": ROOT / "config" / "auth" / "seed" / "admin",
    "operator": ROOT / "config" / "auth" / "seed" / "operator",
    "detector-ai": ROOT / "config" / "auth" / "detector_password",
}
BASE = "https://localhost"
WSS = "wss://localhost"
ORIGIN = "https://localhost"
POLICY = "/api/v1/policy/detection"
COOKIE = "__Host-access_token"
ALERT_SOCKETS = 9
CAMERA_SOCKETS = 6
RACERS = 5
EVENT_WAIT = 3
HEALTH_WAIT = 12
OPEN_TIMEOUT = 20
OK = 200
CREATED = 201
NO_CONTENT = 204
CONFLICT = 409
CONTEXT = ssl.create_default_context(cafile=str(CA))
RESULTS: list[bool] = []


def check(name: str, ok: bool) -> None:
    RESULTS.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")


class Listener:
    def __init__(self, topic: str, token: str) -> None:
        self.topic = topic
        self.token = token
        self.events: list[dict] = []
        self.ready = asyncio.Event()
        self.error = ""

    async def run(self, stop: asyncio.Event) -> None:
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{WSS}/ws/{self.topic}"
        try:
            async with connect(url, ssl=CONTEXT, origin=ORIGIN, additional_headers=headers) as ws:
                self.ready.set()
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except TimeoutError:
                        continue
                    message = json.loads(raw)
                    if message.get("event") != "ping":
                        self.events.append(message)
        except (OSError, WebSocketException) as exc:
            self.error = str(exc)
            self.ready.set()

    def count(self, event: str, key: str, value: str) -> int:
        return sum(
            1
            for message in self.events
            if message.get("event") == event and (message.get("data") or {}).get(key) == value
        )


def read_secrets() -> dict[str, str]:
    return {user: path.read_text().strip() for user, path in SECRETS.items()}


async def login(client: httpx.AsyncClient, user: str, password: str) -> str:
    response = await client.post("/auth/login", json={"username": user, "password": password})
    if response.status_code != OK:
        raise SystemExit(f"login {user} failed with status {response.status_code}")
    token = response.cookies.get(COOKIE)
    if not token:
        raise SystemExit(f"login {user} returned no access cookie")
    client.cookies.clear()
    return token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def alert_body(alert_id: str, camera: str) -> dict:
    return {
        "alert_id": alert_id,
        "session_id": 1,
        "frame_index": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "camera_id": camera,
        "person": {"track_id": 1, "keypoints": []},
        "object": {"class_name": "phone"},
        "severity": "SEVERITY_NOTICE",
        "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
    }


async def stored_alerts(client: httpx.AsyncClient, token: str, camera: str) -> list[str]:
    response = await client.get(
        "/api/v1/alerts", params={"camera_id": camera, "limit": 50}, headers=bearer(token)
    )
    body = response.json()
    items = body.get("items") or body.get("alerts") or body.get("data") or []
    return [item.get("alert_id") for item in items]


async def race(client: httpx.AsyncClient, headers: dict, body: dict) -> list[int]:
    calls = (client.post("/api/v1/alerts", json=body, headers=headers) for _ in range(RACERS))
    return [response.status_code for response in await asyncio.gather(*calls)]


async def alert_checks(client, detector, admin, alerts, run) -> None:
    camera = f"cam-proof-{run}"

    keyed = alert_body(f"proof-keyed-{run}", camera)
    headers = {**bearer(detector), "Idempotency-Key": f"proof-{run}"}
    statuses = await race(client, headers, keyed)
    print(f"     keyed race statuses {sorted(statuses)}")
    check("keyed race answers only 201 or 409", set(statuses) <= {CREATED, CONFLICT})
    check("keyed race created the alert", CREATED in statuses)
    replay = await client.post("/api/v1/alerts", json=keyed, headers=headers)
    check(
        "keyed retry replays the stored alert",
        replay.status_code == CREATED and replay.json().get("alert_id") == keyed["alert_id"],
    )

    plain = alert_body(f"proof-plain-{run}", camera)
    statuses = await race(client, bearer(detector), plain)
    print(f"     unkeyed race statuses {sorted(statuses)}")
    check("unkeyed race answers 201 to every retry", set(statuses) == {CREATED})

    await asyncio.sleep(EVENT_WAIT)
    stored = await stored_alerts(client, admin, camera)
    for alert_id in (keyed["alert_id"], plain["alert_id"]):
        check(f"{alert_id} stored once", stored.count(alert_id) == 1)
        counts = [listener.count("created", "alert_id", alert_id) for listener in alerts]
        print(f"     {alert_id} created events per socket {counts}")
        check(f"{alert_id} reached every socket exactly once", counts == [1] * len(alerts))


async def camera_checks(client, admin, cameras, run) -> None:
    camera_id = f"proof-{run}"
    body = {"camera_id": camera_id, "name": f"proof {run}", "location": "lab"}
    response = await client.post("/api/v1/cameras", json=body, headers=bearer(admin))
    check("camera created", response.status_code == CREATED)
    await asyncio.sleep(HEALTH_WAIT)
    created = [listener.count("created", "camera_id", camera_id) for listener in cameras]
    health = [listener.count("health", "camera_id", camera_id) for listener in cameras]
    print(f"     created per socket {created}, health per socket {health}")
    check("camera created event reached every socket once", created == [1] * len(cameras))
    check("camera health published once across all pods", health == [1] * len(cameras))
    await remove_proof_cameras(client, admin)


async def remove_proof_cameras(client: httpx.AsyncClient, admin: str) -> None:
    listing = (await client.get("/api/v1/cameras", headers=bearer(admin))).json()
    items = listing if isinstance(listing, list) else listing.get("items", [])
    for item in items:
        if not str(item.get("camera_id", "")).startswith("proof-"):
            continue
        removed = await client.delete(f"/api/v1/cameras/{item['camera_id']}", headers=bearer(admin))
        print(f"     removed camera {item['camera_id']} status {removed.status_code}")
        check(f"camera {item['camera_id']} removed", removed.status_code == NO_CONTENT)


async def policy_checks(client, admin) -> None:
    current = (await client.get(POLICY, headers=bearer(admin))).json()
    version = current["version"]
    original = current["policy"]
    changed = json.loads(json.dumps(original))
    threshold = changed["classifier"]["anomaly_threshold"]
    changed["classifier"]["anomaly_threshold"] = round(threshold + 0.01, 2)
    update = await client.put(
        POLICY,
        json={"expected_version": version, "policy": changed},
        headers=bearer(admin),
    )
    check("policy update accepted", update.status_code == OK)
    stale = await client.put(
        POLICY,
        json={"expected_version": version, "policy": changed},
        headers=bearer(admin),
    )
    check("second writer with the old version gets 409", stale.status_code == CONFLICT)
    restore = await client.put(
        POLICY,
        json={"expected_version": version + 1, "policy": original},
        headers=bearer(admin),
    )
    check("policy restored to its original values", restore.status_code == OK)
    final = (await client.get(POLICY, headers=bearer(admin))).json()
    print(f"     policy version {version} -> {final['version']}")


async def main() -> int:
    run = uuid.uuid4().hex[:8]
    secrets = await asyncio.to_thread(read_secrets)
    async with httpx.AsyncClient(base_url=BASE, verify=CONTEXT, timeout=20) as client:
        tokens = {user: await login(client, user, secret) for user, secret in secrets.items()}
        stop = asyncio.Event()
        alerts = [Listener("alerts", tokens["admin"]) for _ in range(ALERT_SOCKETS)]
        cameras = [Listener("cameras", tokens["operator"]) for _ in range(CAMERA_SOCKETS)]
        listeners = alerts + cameras
        tasks = [asyncio.create_task(listener.run(stop)) for listener in listeners]
        await asyncio.wait_for(
            asyncio.gather(*(listener.ready.wait() for listener in listeners)), OPEN_TIMEOUT
        )
        refused = [listener.error for listener in listeners if listener.error]
        check(f"all {len(listeners)} sockets opened", not refused)
        for reason in sorted(set(refused)):
            print(f"     refused: {reason}")
        if not refused:
            await alert_checks(client, tokens["detector-ai"], tokens["admin"], alerts, run)
            await camera_checks(client, tokens["admin"], cameras, run)
            await policy_checks(client, tokens["admin"])
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    print(f"===== scale proof {sum(RESULTS)}/{len(RESULTS)} passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
