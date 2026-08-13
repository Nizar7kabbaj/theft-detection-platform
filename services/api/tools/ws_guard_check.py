from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import sys
from pathlib import Path

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

EDGE = "https://localhost"
WS_BASE = "wss://localhost"
COOKIE_NAME = "__Host-access_token"
ALERTS = "/ws/alerts"
CAMERAS = "/ws/cameras"
ORIGIN_EXACT = "https://localhost"
ORIGIN_SLASH = "https://localhost/"
ORIGIN_UPPER = "https://LOCALHOST"
ORIGIN_DEFAULT_PORT = "https://localhost:443"
ORIGIN_OTHER_PORT = "https://localhost:3001"
ORIGIN_PLAIN_HTTP = "http://localhost"
ORIGIN_FOREIGN = "https://evil.example"
OPEN = "open"
REJECT = "reject"
REJECT_STATUS = 403
REJECT_CLOSE_CODE = 1008
CA_ENV = "WS_CHECK_CA"
CA_DEFAULT = Path(__file__).resolve().parents[3] / "config" / "traefik" / "certs" / "ca.crt"


def _ca_path() -> Path:
    override = os.environ.get(CA_ENV)
    return Path(override) if override else CA_DEFAULT


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(_ca_path()))


def login(username: str, password: str, context: ssl.SSLContext) -> str:
    with httpx.Client(verify=context, timeout=10.0) as client:
        resp = client.post(
            f"{EDGE}/auth/login",
            json={"username": username, "password": password},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"login failed for {username}: http {resp.status_code}")
        token = resp.cookies.get(COOKIE_NAME)
        if not token:
            names = ", ".join(resp.cookies.keys())
            raise RuntimeError(f"login for {username} returned no access cookie, got: {names}")
        return token


async def attempt(
    label: str,
    path: str,
    origin: str | None,
    cookie: str | None,
    expected: str,
    context: ssl.SSLContext,
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
            ssl=context,
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
    parser.add_argument("--denied", default="ws-ml")
    args = parser.parse_args()

    password = os.environ.get("WS_CHECK_PASSWORD")
    if not password:
        print("WS_CHECK_PASSWORD not set", file=sys.stderr)
        return 2

    ca = _ca_path()
    if not ca.is_file():
        print(f"ca certificate not found at {ca}", file=sys.stderr)
        return 2
    context = _ssl_context()

    try:
        operator = login(args.operator, password, context)
        viewer = login(args.viewer, password, context)
        compliance = login(args.compliance, password, context)
        denied = login(args.denied, password, context)
    except RuntimeError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 2
    print("logged in four users")

    cases = [
        ("foreign origin refused", ALERTS, ORIGIN_FOREIGN, operator, REJECT),
        ("missing origin refused", ALERTS, None, operator, REJECT),
        ("plain http origin refused", ALERTS, ORIGIN_PLAIN_HTTP, operator, REJECT),
        ("other port refused", ALERTS, ORIGIN_OTHER_PORT, operator, REJECT),
        ("missing cookie refused", ALERTS, ORIGIN_EXACT, None, REJECT),
        ("exact origin opens", ALERTS, ORIGIN_EXACT, operator, OPEN),
        ("trailing slash origin opens", ALERTS, ORIGIN_SLASH, operator, OPEN),
        ("uppercase host origin opens", ALERTS, ORIGIN_UPPER, operator, OPEN),
        ("explicit default port opens", ALERTS, ORIGIN_DEFAULT_PORT, operator, OPEN),
        ("operator reads cameras", CAMERAS, ORIGIN_EXACT, operator, OPEN),
        ("viewer reads alerts", ALERTS, ORIGIN_EXACT, viewer, OPEN),
        ("viewer reads cameras", CAMERAS, ORIGIN_EXACT, viewer, OPEN),
        ("compliance reads alerts", ALERTS, ORIGIN_EXACT, compliance, OPEN),
        ("compliance refused on cameras", CAMERAS, ORIGIN_EXACT, compliance, REJECT),
        ("ml engineer refused on alerts", ALERTS, ORIGIN_EXACT, denied, REJECT),
        ("ml engineer refused on cameras", CAMERAS, ORIGIN_EXACT, denied, REJECT),
    ]

    results = []
    for label, path, origin, cookie, expected in cases:
        results.append(await attempt(label, path, origin, cookie, expected, context))

    failed = results.count(False)
    print(f"{len(results) - failed} passed, {failed} failed")
    print("every pre-accept refusal is http 403, so the backend log names which check fired")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
