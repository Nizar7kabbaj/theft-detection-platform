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
GOOD_ORIGIN = "http://localhost:3000"
EVIL_ORIGIN = "http://evil.example"
COOKIE_NAME = "__Host-access_token"


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
) -> None:
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = f"{COOKIE_NAME}={cookie}"
    try:
        async with websockets.connect(
            f"{WS_BASE}{path}",
            additional_headers=headers,
            ssl=_ssl_context(),
            open_timeout=10,
        ) as ws:
            await asyncio.sleep(0.2)
            print(f"OPEN    {label}")
            await ws.close()
    except InvalidStatus as exc:
        print(f"REJECT  {label}: http {exc.response.status_code} at handshake")
    except ConnectionClosed as exc:
        print(f"REJECT  {label}: ws close {exc.code} {exc.reason}")
    except Exception as exc:
        print(f"ERROR   {label}: {type(exc).__name__} {exc}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator", required=True)
    parser.add_argument("--compliance", required=True)
    args = parser.parse_args()

    password = os.environ.get("WS_CHECK_PASSWORD")
    if not password:
        print("WS_CHECK_PASSWORD not set", file=sys.stderr)
        return 2

    try:
        op = login(args.operator, password)
        co = login(args.compliance, password)
    except RuntimeError as exc:
        print(f"ERROR   {exc}", file=sys.stderr)
        return 2
    print("logged in both users")

    await attempt("foreign origin, operator cookie, alerts", "/ws/alerts", EVIL_ORIGIN, op)
    await attempt("no origin, operator cookie, alerts", "/ws/alerts", None, op)
    await attempt("good origin, no cookie, alerts", "/ws/alerts", GOOD_ORIGIN, None)
    await attempt("good origin, operator, alerts", "/ws/alerts", GOOD_ORIGIN, op)
    await attempt("good origin, operator, cameras", "/ws/cameras", GOOD_ORIGIN, op)
    await attempt("good origin, compliance, alerts", "/ws/alerts", GOOD_ORIGIN, co)
    await attempt("good origin, compliance, cameras", "/ws/cameras", GOOD_ORIGIN, co)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
