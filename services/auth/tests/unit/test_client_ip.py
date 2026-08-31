from __future__ import annotations

import pytest
from starlette.requests import Request

from app.api.v1.auth import _client_ip, _user_agent
from app.core.config import get_settings

_TRUSTED = '["127.0.0.0/8","::1/128","172.16.0.0/12"]'
_USER_AGENT_LIMIT = 512


@pytest.fixture(autouse=True)
def pinned_proxies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_TRUSTED_PROXIES", _TRUSTED)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _request(
    client_host: str | None = "127.0.0.1",
    forwarded: str | None = None,
    user_agent: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode("latin-1")))
    if user_agent is not None:
        headers.append((b"user-agent", user_agent.encode("latin-1")))
    scope: dict[str, object] = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": headers,
    }
    if client_host is not None:
        scope["client"] = (client_host, 51234)
    return Request(scope)


def test_missing_client_returns_empty():
    assert _client_ip(_request(client_host=None)) == ""


def test_empty_client_host_returns_empty():
    assert _client_ip(_request(client_host="")) == ""


def test_untrusted_peer_is_returned_directly():
    assert _client_ip(_request(client_host="203.0.113.9")) == "203.0.113.9"


def test_untrusted_peer_forwarded_header_is_ignored():
    request = _request(client_host="203.0.113.9", forwarded="198.51.100.7")

    assert _client_ip(request) == "203.0.113.9"


def test_unparseable_peer_is_returned_unchanged():
    assert _client_ip(_request(client_host="not-an-ip")) == "not-an-ip"


def test_trusted_peer_without_forwarded_header_returns_peer():
    assert _client_ip(_request(client_host="127.0.0.1")) == "127.0.0.1"


def test_trusted_peer_with_empty_forwarded_header_returns_peer():
    assert _client_ip(_request(client_host="127.0.0.1", forwarded="")) == "127.0.0.1"


def test_trusted_peer_returns_single_forwarded_client():
    request = _request(client_host="127.0.0.1", forwarded="203.0.113.9")

    assert _client_ip(request) == "203.0.113.9"


def test_rightmost_untrusted_hop_wins():
    request = _request(
        client_host="172.16.0.1",
        forwarded="203.0.113.9, 198.51.100.7, 172.16.0.5",
    )

    assert _client_ip(request) == "198.51.100.7"


def test_spoofed_leading_hops_are_not_trusted():
    request = _request(client_host="127.0.0.1", forwarded="1.1.1.1, 203.0.113.9")

    assert _client_ip(request) == "203.0.113.9"


def test_all_trusted_hops_fall_back_to_peer():
    request = _request(client_host="127.0.0.1", forwarded="172.16.0.5, 127.0.0.9")

    assert _client_ip(request) == "127.0.0.1"


def test_unparseable_hops_are_skipped():
    request = _request(client_host="127.0.0.1", forwarded="203.0.113.9, junk-value")

    assert _client_ip(request) == "203.0.113.9"


def test_only_unparseable_hops_fall_back_to_peer():
    request = _request(client_host="127.0.0.1", forwarded="junk, more-junk")

    assert _client_ip(request) == "127.0.0.1"


def test_empty_hops_are_ignored():
    request = _request(client_host="127.0.0.1", forwarded=" , , ")

    assert _client_ip(request) == "127.0.0.1"


def test_hop_whitespace_is_trimmed():
    request = _request(client_host="127.0.0.1", forwarded="  203.0.113.9  ")

    assert _client_ip(request) == "203.0.113.9"


def test_ipv6_loopback_peer_is_trusted():
    request = _request(client_host="::1", forwarded="203.0.113.9")

    assert _client_ip(request) == "203.0.113.9"


def test_ipv6_forwarded_hop_is_returned():
    request = _request(client_host="127.0.0.1", forwarded="2001:db8::1")

    assert _client_ip(request) == "2001:db8::1"


def test_user_agent_defaults_to_empty():
    assert _user_agent(_request()) == ""


def test_user_agent_is_returned():
    assert _user_agent(_request(user_agent="harness/1.0")) == "harness/1.0"


def test_user_agent_is_truncated_to_column_width():
    request = _request(user_agent="a" * 900)

    assert len(_user_agent(request)) == _USER_AGENT_LIMIT
