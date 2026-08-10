from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import sys
import time

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

EDGE = "https://localhost"
WS_BASE = "wss://localhost"
GOOD_ORIGIN = "http://localhost:3000"
COOKIE_NAME = "__Host-access_token"
CSRF_COOKIE = "__Host-csrf"
CSRF_HEADER = "X-CSRF-Token"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def login(client: httpx.Client, username: str, password: str) -> str:
    resp = client.post(
        f"{EDGE}/auth/login",
        json={"username": username, "password": password},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"login failed: http {resp.status_code}")
    token = client.cookies.get(COOKIE_NAME)
    if not token:
        raise RuntimeError("login returned no access cookie")
    return token


def logout(client: httpx.Client) -> int:
    csrf = client.cookies.get(CSRF_COOKIE, "")
    resp = client.post(
        f"{EDGE}/auth/logout",
        headers={CSRF_HEADER: csrf},
    )
    return resp.status_code


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--wait", type=int, default=90)
    args = parser.parse_args()

    password = os.environ.get("WS_CHECK_PASSWORD")
    if not password:
        print("WS_CHECK_PASSWORD not set", file=sys.stderr)
        return 2

    with httpx.Client(verify=False, timeout=10.0) as client:
        try:
            token = login(client, args.user, password)
        except RuntimeError as exc:
            print(f"ERROR   {exc}", file=sys.stderr)
            return 2
        print("logged in")

        try:
            ws = await websockets.connect(
                f"{WS_BASE}/ws/alerts",
                additional_headers={
                    "Origin": GOOD_ORIGIN,
                    "Cookie": f"{COOKIE_NAME}={token}",
                },
                ssl=_ssl_context(),
                open_timeout=10,
            )
        except Exception as exc:
            print(f"ERROR   could not open socket: {type(exc).__name__} {exc}")
            return 1
        print("OPEN    socket live, revoking session now")

        code = logout(client)
        print(f"logout returned http {code}")
        if code != 200:
            print("ERROR   logout did not succeed, revocation never happened")
            await ws.close()
            return 1

        started = time.monotonic()
        frames = 0
        try:
            while True:
                remaining = args.wait - (time.monotonic() - started)
                if remaining <= 0:
                    print(
                        f"ERROR   socket still open after {args.wait}s, "
                        f"revocation not enforced ({frames} frames seen)"
                    )
                    await ws.close()
                    return 1
                await asyncio.wait_for(ws.recv(), timeout=remaining)
                frames += 1
        except ConnectionClosed as exc:
            elapsed = time.monotonic() - started
            print(
                f"CLOSED  after {elapsed:.1f}s: ws close {exc.code} "
                f"{exc.reason} ({frames} frames before close)"
            )
            return 0
        except TimeoutError:
            print(
                f"ERROR   socket still open after {args.wait}s, "
                f"revocation not enforced ({frames} frames seen)"
            )
            await ws.close()
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
