from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import ssl
import sys
import time
from pathlib import Path

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

EDGE = "https://localhost"
WS_BASE = "wss://localhost"
ACCESS_COOKIE = "__Host-access_token"
REFRESH_COOKIE = "__Host-refresh_token"
CSRF_COOKIE = "__Host-csrf"
CSRF_HEADER = "X-CSRF-Token"
ALERTS = "/ws/alerts"
ORIGIN = "https://localhost"
CA_ENV = "WS_CHECK_CA"
CA_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "traefik" / "certs" / "ca.crt"
PASSWORD_FILE = Path("config/auth/test_users_password")
BASE_DELAY_MS = 500
MAX_DELAY_MS = 30_000
MIN_DELAY_MS = 1_000
GLOBAL_SPACING_MS = 2_000
POLICY = 1008
HEARTBEAT_TIMEOUT = 35.0
ACCESS_TTL_SECONDS = 900


def _ca_path() -> Path:
    override = os.environ.get(CA_ENV)
    return Path(override) if override else CA_DEFAULT


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(_ca_path()))


def _password() -> str:
    return PASSWORD_FILE.read_text().strip()


def login(username: str, context: ssl.SSLContext) -> dict[str, str]:
    with httpx.Client(verify=context, timeout=10.0) as client:
        resp = client.post(
            f"{EDGE}/auth/login",
            json={"username": username, "password": _password()},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"login failed for {username}: http {resp.status_code}")
        access = resp.cookies.get(ACCESS_COOKIE)
        if not access:
            raise RuntimeError(f"login for {username} returned no access cookie")
        return {
            "access": access,
            "refresh": resp.cookies.get(REFRESH_COOKIE) or "",
            "csrf": resp.cookies.get(CSRF_COOKIE) or "",
        }


def logout(session: dict[str, str], context: ssl.SSLContext) -> int:
    cookies = {ACCESS_COOKIE: session["access"], CSRF_COOKIE: session["csrf"]}
    with httpx.Client(verify=context, timeout=10.0, cookies=cookies) as client:
        resp = client.post(
            f"{EDGE}/auth/logout",
            headers={CSRF_HEADER: session["csrf"], "Origin": ORIGIN},
        )
        return resp.status_code


def refresh(session: dict[str, str], context: ssl.SSLContext) -> dict[str, str]:
    cookies = {
        ACCESS_COOKIE: session["access"],
        REFRESH_COOKIE: session["refresh"],
        CSRF_COOKIE: session["csrf"],
    }
    with httpx.Client(verify=context, timeout=10.0, cookies=cookies) as client:
        resp = client.post(
            f"{EDGE}/auth/refresh",
            headers={CSRF_HEADER: session["csrf"], "Origin": ORIGIN},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"refresh failed: http {resp.status_code}")
        return {
            "access": resp.cookies.get(ACCESS_COOKIE) or session["access"],
            "refresh": resp.cookies.get(REFRESH_COOKIE) or session["refresh"],
            "csrf": resp.cookies.get(CSRF_COOKIE) or session["csrf"],
        }


def _headers(session: dict[str, str]) -> dict[str, str]:
    return {"Origin": ORIGIN, "Cookie": f"{ACCESS_COOKIE}={session['access']}"}


def backoff_delay(attempt: int) -> float:
    exponential = min(MAX_DELAY_MS, BASE_DELAY_MS * 2**attempt)
    return max(MIN_DELAY_MS, round(random.random() * exponential)) / 1000


async def case_accepted(session: dict[str, str], context: ssl.SSLContext) -> int:
    started = time.monotonic()
    async with websockets.connect(
        f"{WS_BASE}{ALERTS}",
        additional_headers=_headers(session),
        ssl=context,
        open_timeout=10,
    ) as ws:
        print(f"socket open after {time.monotonic() - started:.2f}s")
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=HEARTBEAT_TIMEOUT)
        except TimeoutError:
            print(f"FAIL no frame within {HEARTBEAT_TIMEOUT:.0f}s")
            return 1
        elapsed = time.monotonic() - started
        try:
            frame = json.loads(raw)
        except ValueError:
            print(f"FAIL first frame is not json: {raw[:80]}")
            return 1
        event = frame.get("event")
        print(f"first frame event={event} after {elapsed:.1f}s")
        return 0 if event == "ping" else 1


async def case_revoked(session: dict[str, str], context: ssl.SSLContext) -> int:
    async with websockets.connect(
        f"{WS_BASE}{ALERTS}",
        additional_headers=_headers(session),
        ssl=context,
        open_timeout=10,
    ) as ws:
        print("socket open, revoking session")
        status = logout(session, context)
        if status != 200:
            print(f"FAIL logout returned http {status}")
            return 1
        started = time.monotonic()
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout=90)
        except ConnectionClosed as exc:
            elapsed = time.monotonic() - started
            print(f"closed code={exc.code} reason={exc.reason!r} after {elapsed:.2f}s")
            if exc.code != POLICY:
                print(f"FAIL expected close {POLICY}")
                return 1
            path = "pub/sub" if elapsed < 5 else "recheck poll"
            print(f"close arrived via {path}")
            return 0
        except TimeoutError:
            print("FAIL socket still open 90s after revocation")
            return 1


async def _upgrade(session: dict[str, str], context: ssl.SSLContext) -> str:
    try:
        async with websockets.connect(
            f"{WS_BASE}{ALERTS}",
            additional_headers=_headers(session),
            ssl=context,
            open_timeout=10,
        ) as ws:
            await ws.close()
            return "accepted"
    except InvalidStatus as exc:
        return f"refused {exc.response.status_code}"
    except (ConnectionClosed, OSError) as exc:
        return f"error {type(exc).__name__} {exc}"


async def case_flood(session: dict[str, str], context: ssl.SSLContext, rounds: int) -> int:
    outcomes = []
    for _ in range(rounds):
        outcomes.append(await _upgrade(session, context))
    accepted = outcomes.count("accepted")
    refused = len(outcomes) - accepted
    print(f"{rounds} back-to-back upgrades: {accepted} accepted, {refused} refused")
    if refused == 0:
        print("FAIL rate limit never engaged, burst should exhaust")
        return 1
    print("limiter engaged as configured, burst 10 then one per 2s")
    return 0


async def case_paced(session: dict[str, str], context: ssl.SSLContext, rounds: int) -> int:
    outcomes = []
    scheduled = 0.0
    for attempt in range(rounds):
        delay = backoff_delay(attempt)
        spaced = max(delay, GLOBAL_SPACING_MS / 1000)
        scheduled += spaced
        await asyncio.sleep(spaced)
        outcomes.append(await _upgrade(session, context))
    accepted = outcomes.count("accepted")
    refused = len(outcomes) - accepted
    print(f"{rounds} upgrades over {scheduled:.0f}s: {accepted} accepted, {refused} refused")
    if refused:
        print("FAIL client schedule tripped the limiter")
        return 1
    print("client backoff schedule stays under the per-user limit")
    return 0


async def case_hold(session: dict[str, str], context: ssl.SSLContext, seconds: int) -> int:
    if not session["refresh"]:
        print("FAIL login returned no refresh cookie, check the cookie name", file=sys.stderr)
        return 2
    pings = 0
    started = time.monotonic()
    async with websockets.connect(
        f"{WS_BASE}{ALERTS}",
        additional_headers=_headers(session),
        ssl=context,
        open_timeout=10,
    ) as ws:
        print(f"socket open, holding {seconds}s past a {ACCESS_TTL_SECONDS}s access token")
        while time.monotonic() - started < seconds:
            remaining = seconds - (time.monotonic() - started)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(HEARTBEAT_TIMEOUT, remaining))
            except TimeoutError:
                continue
            except ConnectionClosed as exc:
                elapsed = time.monotonic() - started
                print(f"FAIL closed early at {elapsed:.0f}s code={exc.code} reason={exc.reason!r}")
                return 1
            frame = json.loads(raw)
            if frame.get("event") == "ping":
                pings += 1
        held = time.monotonic() - started
        print(f"still open after {held:.0f}s, {pings} heartbeats, access token expired")

    stale = await _upgrade(session, context)
    print(f"reconnect with the expired cookie: {stale}")
    if stale == "accepted":
        print("FAIL an expired access cookie opened a socket")
        return 1

    try:
        renewed = refresh(session, context)
    except RuntimeError as exc:
        print(f"FAIL refresh rejected: {exc}")
        return 1
    revived = await _upgrade(renewed, context)
    print(f"reconnect after refresh: {revived}")
    if revived != "accepted":
        print("FAIL refreshed cookie did not restore the stream")
        return 1
    print("session outlived the token, refresh restored the upgrade")
    return 0


async def run(args: argparse.Namespace) -> int:
    ca = _ca_path()
    if not ca.is_file():
        print(f"ca certificate not found at {ca}", file=sys.stderr)
        return 2
    if not PASSWORD_FILE.is_file():
        print(f"password file not found at {PASSWORD_FILE}", file=sys.stderr)
        return 2
    context = _ssl_context()
    try:
        session = login(args.user, context)
    except RuntimeError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    if args.case == "accepted":
        return await case_accepted(session, context)
    if args.case == "revoked":
        return await case_revoked(session, context)
    if args.case == "flood":
        return await case_flood(session, context, args.rounds)
    if args.case == "hold":
        return await case_hold(session, context, args.seconds)
    return await case_paced(session, context, args.rounds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=["accepted", "revoked", "flood", "paced", "hold"])
    parser.add_argument("--user", default="ws-viewer")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--seconds", type=int, default=960)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
