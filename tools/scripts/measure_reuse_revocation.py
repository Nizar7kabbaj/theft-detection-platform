from __future__ import annotations

import asyncio
import json
import time
import urllib.error
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


def _jar_to_dict(response) -> dict[str, str]:
    jar = SimpleCookie()
    for header in response.headers.get_all("Set-Cookie") or []:
        jar.load(header)
    return {name: morsel.value for name, morsel in jar.items()}


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
        cookies = _jar_to_dict(response)
    missing = [n for n in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE) if n not in cookies]
    if missing:
        raise SystemExit(f"missing cookies {missing}")
    return cookies


def refresh(cookies: dict[str, str]) -> tuple[int, dict[str, str]]:
    header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    request = urllib.request.Request(
        f"{AUTH_URL}/auth/refresh",
        data=b"",
        headers={
            "Cookie": header,
            CSRF_HEADER: cookies[CSRF_COOKIE],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, _jar_to_dict(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}


async def run() -> None:
    original = login()
    print(f"login ok user={USERNAME}")
    headers = {
        "Origin": ORIGIN,
        "Cookie": f"{ACCESS_COOKIE}={original[ACCESS_COOKIE]}",
    }
    async with websockets.connect(WS_URL, additional_headers=headers) as socket:
        print("websocket open")
        await asyncio.sleep(1.0)

        status, rotated = refresh(dict(original))
        print(f"first refresh status={status}")
        if status != 200:
            raise SystemExit("rotation failed, cannot test reuse")

        started = time.monotonic()
        replayed, _ = refresh(dict(original))
        print(f"replayed refresh status={replayed}")

        try:
            while True:
                await socket.recv()
        except websockets.exceptions.ConnectionClosed as exc:
            elapsed = time.monotonic() - started
            print(f"closed after {elapsed:.3f}s code={exc.code} reason={exc.reason}")
            return


if __name__ == "__main__":
    asyncio.run(run())
