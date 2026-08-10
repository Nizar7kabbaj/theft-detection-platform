from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import ssl
import sys
import time

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

EDGE = "https://localhost"
WS_BASE = "wss://localhost"
COOKIE_NAME = "__Host-access_token"
ORIGIN = "http://localhost:3000"


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
            raise RuntimeError(f"login failed: http {resp.status_code}")
        token = resp.cookies.get(COOKIE_NAME)
        if not token:
            raise RuntimeError("login returned no access cookie")
        return token


def token_lifetime(token: str) -> int:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return int(claims["exp"]) - int(claims["iat"])


async def watch(token: str, hold_seconds: int) -> int:
    headers = {
        "Origin": ORIGIN,
        "Cookie": f"{COOKIE_NAME}={token}",
    }
    started = time.monotonic()
    async with websockets.connect(
        f"{WS_BASE}/ws/alerts",
        additional_headers=headers,
        ssl=_ssl_context(),
        open_timeout=10,
    ) as ws:
        print("socket open, holding")
        while True:
            elapsed = time.monotonic() - started
            remaining = hold_seconds - elapsed
            if remaining <= 0:
                print(f"still open after {int(elapsed)}s")
                await ws.close()
                return 0
            try:
                await asyncio.wait_for(ws.recv(), timeout=min(remaining, 10.0))
            except TimeoutError:
                print(f"  {int(time.monotonic() - started)}s open")
            except ConnectionClosed as exc:
                print(
                    f"closed after {int(time.monotonic() - started)}s: "
                    f"code {exc.code} reason {exc.reason}"
                )
                return 1


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="ws-operator")
    parser.add_argument("--hold", type=int, default=150)
    parser.add_argument("--allow-long-token", action="store_true")
    args = parser.parse_args()

    password = os.environ.get("WS_CHECK_PASSWORD")
    if not password:
        print("WS_CHECK_PASSWORD not set", file=sys.stderr)
        return 2

    try:
        token = login(args.username, password)
    except RuntimeError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 2

    ttl = token_lifetime(token)
    print(f"access token lifetime {ttl}s, holding socket {args.hold}s")
    if ttl >= args.hold and not args.allow_long_token:
        print("token outlives the hold, test proves nothing", file=sys.stderr)
        return 2

    return await watch(token, args.hold)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
