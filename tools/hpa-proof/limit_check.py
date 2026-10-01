import http.client
import json
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from http.cookies import SimpleCookie
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CA = ROOT / "config" / "traefik" / "certs" / "ca.crt"
PASSWORD = ROOT / "config" / "auth" / "seed" / "viewer"
HOST = "localhost"
PATH = "/api/v1/alerts/count"
COOKIE = "__Host-access_token"
BURST = 80
STEADY = 150
STEADY_RATE = 8
EDGE_REFILL_SECONDS = 6
OK = 200
TOO_MANY = 429
CONTEXT = ssl.create_default_context(cafile=str(CA))


def request(
    method: str, path: str, body: bytes | None, headers: dict
) -> tuple[int, Message, bytes]:
    connection = http.client.HTTPSConnection(HOST, 443, context=CONTEXT, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.headers, response.read()
    finally:
        connection.close()


def login() -> str:
    secret = PASSWORD.read_text().strip()
    body = json.dumps({"username": "viewer", "password": secret}).encode()
    status, headers, _ = request("POST", "/auth/login", body, {"Content-Type": "application/json"})
    if status != OK:
        raise SystemExit(f"login failed with status {status}")
    jar = SimpleCookie()
    for raw in headers.get_all("Set-Cookie") or []:
        jar.load(raw)
    if COOKIE not in jar:
        raise SystemExit("login returned no access cookie")
    return jar[COOKIE].value


def classify(result: tuple[int, Message, bytes]) -> str:
    status, headers, body = result
    if status != TOO_MANY:
        return str(status)
    if b"local_rate_limited" in body:
        return "429 edge"
    if b"rate limit exceeded" in body and headers.get("Retry-After"):
        return "429 app"
    return "429 other"


def tally(results: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        counts[item] = counts.get(item, 0) + 1
    return counts


def report(ok: bool, text: str) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {text}")


def main() -> int:
    auth = {"Authorization": f"Bearer {login()}"}

    def probe(_: int) -> str:
        return classify(request("GET", PATH, None, auth))

    with ThreadPoolExecutor(max_workers=BURST) as pool:
        burst = tally(list(pool.map(probe, range(BURST))))
    print("burst", burst)
    time.sleep(EDGE_REFILL_SECONDS)
    steady_results = []
    for index in range(STEADY):
        steady_results.append(probe(index))
        time.sleep(1 / STEADY_RATE)
    steady = tally(steady_results)
    print("steady", steady)
    edge_ok = burst.get("429 edge", 0) > 0
    app_ok = steady.get("429 app", 0) > 0 and steady.get("429 edge", 0) == 0
    report(edge_ok, "edge limiter cuts a burst from one address")
    report(app_ok, "app limiter answers 429 with retry-after once the user budget is spent")
    return 0 if edge_ok and app_ok else 1


if __name__ == "__main__":
    sys.exit(main())
