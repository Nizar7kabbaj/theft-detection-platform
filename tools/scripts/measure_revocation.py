from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path

import websockets

AUTH_URL = "http://127.0.0.1:8002"
WS_URL = "ws://127.0.0.1:8001/ws/alerts"
ORIGIN = "http://localhost:3000"
USERNAME = "ws-operator"
PASSWORD_FILE = Path("config/auth/test_users_password")
ACCESS_COOKIE = "__Host-access_token"
REFRESH_COOKIE = "__Host-refresh_token"
CSRF_COOKIE = "__Host-csrf"
CSRF_HEADER = "X-CSRF-Token"


def login() -> dict[str, str]:
    password = PASSWORD_FILE.read_text().strip()
    body = json.dumps({"username": USERNAME, "password": password}).encode()
    request = urllib.request.Request(
        f"{AUTH_URL}/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        if response.status != 200:
            raise SystemExit(f"login failed status={response.status}")
        jar = SimpleCookie()
        for header in response.headers.get_all("Set-Cookie") or []:
            jar.load(header)
    missing = [name for name in (ACCESS_COOKIE, CSRF_COOKIE) if name not in jar]
    if missing:
        raise SystemExit(f"missing cookies {missing}")
    return {name: morsel.value for name, morsel in jar.items()}


def logout(cookies: dict[str, str]) -> int:
    header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    request = urllib.request.Request(
        f"{AUTH_URL}/auth/logout",
        data=b"",
        headers={
            "Cookie": header,
            CSRF_HEADER: cookies[CSRF_COOKIE],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return response.status


async def run() -> None:
    cookies = login()
    print(f"login ok user={USERNAME}")
    headers = {
        "Origin": ORIGIN,
        "Cookie": f"{ACCESS_COOKIE}={cookies[ACCESS_COOKIE]}",
    }
    async with websockets.connect(WS_URL, additional_headers=headers) as socket:
        print("websocket open")
        await asyncio.sleep(1.0)
        started = time.monotonic()
        status = logout(cookies)
        print(f"logout status={status}")
        try:
            while True:
                await socket.recv()
        except websockets.exceptions.ConnectionClosed as exc:
            elapsed = time.monotonic() - started
            print(f"closed after {elapsed:.3f}s code={exc.code} reason={exc.reason}")
            return
    print("socket never closed", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(run())
