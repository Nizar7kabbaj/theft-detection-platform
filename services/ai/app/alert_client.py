from __future__ import annotations

import logging
import threading
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_HTTP_OK = 200
_HTTP_CREATED = 201


class AlertClient:
    def __init__(
        self,
        api_base_url: str,
        auth_base_url: str,
        username: str,
        password_file: str,
        access_cookie_name: str,
        csrf_cookie_name: str,
        csrf_header_name: str,
        verify: str | bool,
        timeout_seconds: float,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._auth_base_url = auth_base_url.rstrip("/")
        self._username = username
        self._password_file = password_file
        self._access_cookie_name = access_cookie_name
        self._csrf_cookie_name = csrf_cookie_name
        self._csrf_header_name = csrf_header_name
        self._verify = verify
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._token: str | None = None

    def _password(self) -> str:
        return Path(self._password_file).read_text().strip()

    def _fetch_token(self) -> str | None:
        session = requests.Session()
        try:
            response = session.post(
                f"{self._auth_base_url}/auth/login",
                json={"username": self._username, "password": self._password()},
                timeout=self._timeout,
                verify=self._verify,
            )
        except requests.RequestException as exc:
            logger.warning("auth login failed: %s", exc)
            return None
        finally:
            session.close()
        if response.status_code != _HTTP_OK:
            logger.warning("auth login rejected status=%d", response.status_code)
            return None
        token = self._token_from_response(response)
        if token is None:
            logger.warning("auth login returned no access token")
        return token

    def _token_from_response(self, response: requests.Response) -> str | None:
        for header in response.raw.headers.getlist("set-cookie"):
            name, _, remainder = header.partition("=")
            if name.strip() != self._access_cookie_name:
                continue
            value = remainder.split(";", 1)[0].strip()
            if value:
                return value
        return None

    def _connect(self) -> str | None:
        with self._lock:
            if self._token is None:
                self._token = self._fetch_token()
            return self._token

    def _reset(self) -> None:
        with self._lock:
            self._token = None

    def send(self, payload: dict[str, object]) -> bool:
        for attempt in (1, 2):
            token = self._connect()
            if token is None:
                return False
            try:
                response = requests.post(
                    f"{self._api_base_url}/api/v1/alerts",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=self._timeout,
                    verify=self._verify,
                )
            except requests.RequestException as exc:
                logger.warning("alert post failed: %s", exc)
                self._reset()
                continue
            if response.status_code in (401, 403) and attempt == 1:
                logger.info("alert post rejected status=%d, retrying", response.status_code)
                self._reset()
                continue
            if response.status_code != _HTTP_CREATED:
                logger.warning(
                    "alert post rejected status=%d body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return False
            return True
        return False

    def close(self) -> None:
        self._reset()
