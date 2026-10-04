from __future__ import annotations

import asyncio
import base64
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path

import websockets

AUTH_URL = "http://127.0.0.1:8002"
WS_URL = "ws://127.0.0.1:8001/ws/alerts"
ORIGIN = "http://localhost:3000"
USERNAME = "ws-operator"
PASSWORD_FILE = Path("config/auth/test_users_password")
ACCESS_COOKIE = "__Host-access_token"
CSRF_COOKIE = "__Host-csrf"
AUTH_TARGET = "auth:50053"
SID_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,128}")

REVOKE_SNIPPET = """
import os

import grpc
from app.grpc_gen import auth_pb2, auth_pb2_grpc

with open("/run/secrets/api_tls_ca", "rb") as handle:
    ca = handle.read()
with open("/run/secrets/api_tls_cert", "rb") as handle:
    cert = handle.read()
with open("/run/secrets/api_tls_key", "rb") as handle:
    key = handle.read()

credentials = grpc.ssl_channel_credentials(ca, key, cert)
with grpc.secure_channel(os.environ["REVOKE_TARGET"], credentials) as channel:
    stub = auth_pb2_grpc.AuthServiceStub(channel)
    reply = stub.RevokeSession(
        auth_pb2.RevokeSessionRequest(
            session_id=os.environ["REVOKE_SID"],
            reason="operator revocation drill",
            revoked_by="measure-grpc-revocation",
        ),
        timeout=5.0,
    )
    print(reply.revoked)
"""


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
        if response.status != HTTPStatus.OK:
            raise SystemExit(f"login failed status={response.status}")
        jar = SimpleCookie()
        for header in response.headers.get_all("Set-Cookie") or []:
            jar.load(header)
    missing = [name for name in (ACCESS_COOKIE, CSRF_COOKIE) if name not in jar]
    if missing:
        raise SystemExit(f"missing cookies {missing}")
    return {name: morsel.value for name, morsel in jar.items()}


def session_id_from(token: str) -> str:
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(padded))
    sid = claims.get("sid")
    if not sid:
        raise SystemExit("access token carries no sid claim")
    return sid


def revoke(sid: str) -> str:
    if not SID_PATTERN.fullmatch(sid):
        raise SystemExit("session id has an unexpected shape, refusing to send it")
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker not found on PATH")
    result = subprocess.run(
        [
            docker,
            "compose",
            "exec",
            "-T",
            "-e",
            f"REVOKE_SID={sid}",
            "-e",
            f"REVOKE_TARGET={AUTH_TARGET}",
            "backend",
            "python",
            "-c",
            REVOKE_SNIPPET,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"revoke call failed: {result.stderr.strip()}")
    return result.stdout.strip()


async def run() -> None:
    cookies = login()
    sid = session_id_from(cookies[ACCESS_COOKIE])
    print(f"login ok user={USERNAME} sid={sid}")
    headers = {
        "Origin": ORIGIN,
        "Cookie": f"{ACCESS_COOKIE}={cookies[ACCESS_COOKIE]}",
    }
    async with websockets.connect(WS_URL, additional_headers=headers) as socket:
        print("websocket open")
        await asyncio.sleep(1.0)
        started = time.monotonic()
        revoked = revoke(sid)
        print(f"revoke reply revoked={revoked}")
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
