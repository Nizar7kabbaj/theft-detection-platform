import http.client
import json
import ssl
import time
import uuid
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EDGE_CA = REPO / "config" / "traefik" / "certs" / "ca.crt"
PASSWORD_FILE = REPO / "config" / "auth" / "detector_password"
HOST = "localhost"
USERNAME = "detector-ai"
ACCESS_COOKIE = "__Host-access_token"
HTTP_OK = 200
HTTP_CREATED = 201


def call(method, path, body, headers):
    context = ssl.create_default_context(cafile=str(EDGE_CA))
    connection = http.client.HTTPSConnection(HOST, context=context, timeout=10)
    try:
        connection.request(
            method,
            path,
            body=json.dumps(body),
            headers={"Content-Type": "application/json", **headers},
        )
        response = connection.getresponse()
        text = response.read().decode("utf-8", errors="replace")
        return response.status, response.headers.get_all("Set-Cookie") or [], text
    finally:
        connection.close()


def login():
    password = PASSWORD_FILE.read_text().strip()
    status, cookies, _ = call(
        "POST", "/auth/login", {"username": USERNAME, "password": password}, {}
    )
    if status != HTTP_OK:
        raise SystemExit(f"login failed with status {status}")
    jar = SimpleCookie()
    for cookie in cookies:
        jar.load(cookie)
    if ACCESS_COOKIE not in jar:
        raise SystemExit("login returned no access cookie")
    return jar[ACCESS_COOKIE].value


def send_alert(token):
    alert_id = f"smoke-path-{int(time.time())}"
    body = {
        "alert_id": alert_id,
        "session_id": 1,
        "frame_index": 42,
        "occurred_at": datetime.now(UTC).isoformat(),
        "camera_id": "cam-smoke",
        "severity": "SEVERITY_WARNING",
    }
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}
    status, _, text = call("POST", "/api/v1/alerts", body, headers)
    if status != HTTP_CREATED:
        raise SystemExit(f"alert create failed with status {status}: {text[:200]}")
    return alert_id


def main():
    alert_id = send_alert(login())
    print(f"alert accepted through the gateway: {alert_id}")


if __name__ == "__main__":
    main()
