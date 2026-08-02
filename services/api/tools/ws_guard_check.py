from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import sys

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

EDGE = "https://localhost"
WS_BASE = "wss://localhost"
COOKIE_NAME = "__Host-access_token"

ALERTS = "/ws/alerts"
CAMERAS = "/ws/cameras"

ORIGIN_EXACT = "http://localhost:3000"
ORIGIN_SLASH = "http://localhost:3000/"
ORIGIN_UPPER = "http://LOCALHOST:3000"
ORIGIN_OTHER_PORT = "http://localhost:3001"
ORIGIN_FOREIGN = "http://evil.example"

OPEN = "open"
REJECT = "reject"

REJECT_STATUS = 403
REJECT_CLOSE_CODE = 1008


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def login(username: str, password: str) -> str:
    with httpx.Client(verify=False, timeout=10.0) as client:
        resp = client.post(
            f"{EDGE}/auth/login",
            json={"username": username, "password": password},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"login failed for {username}: http {resp.status_code}"
            )
        token = resp.cookies.get(COOKIE_NAME)
        if not token:
            names = ", ".join(resp.cookies.keys())
            raise RuntimeError(
                f"login for {username} returned no access cookie, got: {names}"
            )
        return token


async def attempt(
    label: str,
    path: str,
    origin: str | None,
    cookie: str | None,
    expected: str,
) -> bool:
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = f"{COOKIE_NAME}={cookie}"
    expected_reject = False
    try:
        async with websockets.connect(
            f"{WS_BASE}{path}",
            additional_headers=headers,
            ssl=_ssl_context(),
            open_timeout=10,
        ) as ws:
            await asyncio.sleep(0.2)
            outcome = OPEN
            detail = "socket open"
            await ws.close()
    except InvalidStatus as exc:
        outcome = REJECT
        status = exc.response.status_code
        expected_reject = status == REJECT_STATUS
        detail = f"http {status} at handshake"
    except ConnectionClosed as exc:
        outcome = REJECT
        expected_reject = exc.code == REJECT_CLOSE_CODE
        detail = f"ws close {exc.code} {exc.reason}"
    except Exception as exc:
        print(f"ERROR  {label}: {type(exc).__name__} {exc}")
        return False
    if outcome != expected:
        print(f"FAIL   {label}: expected {expected}, got {outcome} ({detail})")
        return False
    if outcome == REJECT and not expected_reject:
        print(
            f"FAIL   {label}: refused, but not by the guard "
            f"(want http {REJECT_STATUS} or close {REJECT_CLOSE_CODE}, got {detail})"
        )
        return False
    print(f"ok     {label}: {detail}")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator", default="ws-operator")
    parser.add_argument("--viewer", default="ws-viewer")
    parser.add_argument("--compliance", default="ws-compliance")
    args = parser.parse_args()

    password = os.environ.get("WS_CHECK_PASSWORD")
    if not password:
        print("WS_CHECK_PASSWORD not set", file=sys.stderr)
        return 2

    try:
        operator = login(args.operator, password)
        viewer = login(args.viewer, password)
        compliance = login(args.compliance, password)
    except RuntimeError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 2

    print("logged in three users")

    cases = [
        ("foreign origin refused", ALERTS, ORIGIN_FOREIGN, operator, REJECT),
        ("missing origin refused", ALERTS, None, operator, REJECT),
        ("missing cookie refused", ALERTS, ORIGIN_EXACT, None, REJECT),
        ("other port refused", ALERTS, ORIGIN_OTHER_PORT, operator, REJECT),
        ("exact origin opens", ALERTS, ORIGIN_EXACT, operator, OPEN),
        ("trailing slash origin opens", ALERTS, ORIGIN_SLASH, operator, OPEN),
        ("uppercase host origin opens", ALERTS, ORIGIN_UPPER, operator, OPEN),
        ("operator reads cameras", CAMERAS, ORIGIN_EXACT, operator, OPEN),
        ("viewer reads alerts", ALERTS, ORIGIN_EXACT, viewer, OPEN),
        ("viewer reads cameras", CAMERAS, ORIGIN_EXACT, viewer, OPEN),
        ("compliance reads alerts", ALERTS, ORIGIN_EXACT, compliance, OPEN),
        ("compliance refused on cameras", CAMERAS, ORIGIN_EXACT, compliance, REJECT),
    ]

    results = []
    for label, path, origin, cookie, expected in cases:
        results.append(await attempt(label, path, origin, cookie, expected))

    failed = results.count(False)
    print(f"{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
