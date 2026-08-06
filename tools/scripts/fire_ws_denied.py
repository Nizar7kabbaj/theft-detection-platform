from __future__ import annotations
import asyncio
import json
import sys
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
import websockets

AUTH_URL = "http://127.0.0.1:8002"
WS_URL = "ws://127.0.0.1:8001/ws/alerts"
ORIGIN = "http://localhost:3000"
USERNAME = "ws-ml"
PASSWORD_FILE = Path("config/auth/test_users_password")
ACCESS_COOKIE = "__Host-access_token"


def login() -> str:
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
    if ACCESS_COOKIE not in jar:
        raise SystemExit("access cookie not returned")
    return jar[ACCESS_COOKIE].value


async def attempt(access: str) -> None:
    headers = {
        "Origin": ORIGIN,
        "Cookie": f"{ACCESS_COOKIE}={access}",
    }
    try:
        async with websockets.connect(WS_URL, additional_headers=headers):
            print("connection accepted, no denial fired")
    except websockets.exceptions.InvalidStatus as exc:
        print(f"upgrade refused http status {exc.response.status_code}")
    except websockets.exceptions.ConnectionClosed as exc:
        print(f"closed code {exc.code} reason {exc.reason}")


def main() -> None:
    access = login()
    print("login ok, cookie captured")
    asyncio.run(attempt(access))


if __name__ == "__main__":
    main()
