from __future__ import annotations

from http.cookies import SimpleCookie

from fastapi import Response

from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies, new_csrf_token, set_auth_cookies

_CSRF_TOKEN_MIN_LENGTH = 40
_COOKIE_COUNT = 3
_ACCESS_MAX_AGE = 900
_REFRESH_MAX_AGE = 1209600


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


def _parsed(response: Response) -> dict[str, SimpleCookie]:
    parsed: dict[str, SimpleCookie] = {}
    for header in _set_cookie_headers(response):
        jar = SimpleCookie()
        jar.load(header)
        for name in jar:
            parsed[name] = jar
    return parsed


def _populated_response() -> Response:
    response = Response()
    set_auth_cookies(
        response=response,
        access_token="access-token-value",
        refresh_token="refresh-token-value",
        csrf_token="csrf-token-value",
        refresh_max_age=_REFRESH_MAX_AGE,
        access_max_age=_ACCESS_MAX_AGE,
    )
    return response


def test_new_csrf_token_is_unique_and_long():
    first = new_csrf_token()

    assert first != new_csrf_token()
    assert len(first) >= _CSRF_TOKEN_MIN_LENGTH


def test_set_auth_cookies_emits_three_cookies():
    assert len(_set_cookie_headers(_populated_response())) == _COOKIE_COUNT


def test_cookie_names_come_from_settings():
    settings = get_settings()
    names = set(_parsed(_populated_response()))

    assert names == {
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    }


def test_cookie_values_are_carried_through():
    settings = get_settings()
    jars = _parsed(_populated_response())

    assert jars[settings.access_cookie_name][settings.access_cookie_name].value == (
        "access-token-value"
    )
    assert jars[settings.refresh_cookie_name][settings.refresh_cookie_name].value == (
        "refresh-token-value"
    )
    assert jars[settings.csrf_cookie_name][settings.csrf_cookie_name].value == "csrf-token-value"


def test_every_cookie_is_secure_and_root_pathed_without_domain():
    for header in _set_cookie_headers(_populated_response()):
        jar = SimpleCookie()
        jar.load(header)
        for name in jar:
            assert jar[name]["secure"] is True
            assert jar[name]["path"] == "/"
            assert jar[name]["domain"] == ""


def test_host_prefixed_names_satisfy_prefix_rules():
    settings = get_settings()
    prefixed = [
        name
        for name in (
            settings.access_cookie_name,
            settings.refresh_cookie_name,
            settings.csrf_cookie_name,
        )
        if name.startswith("__Host-")
    ]

    assert prefixed
    jars = _parsed(_populated_response())
    for name in prefixed:
        assert jars[name][name]["secure"] is True
        assert jars[name][name]["path"] == "/"
        assert jars[name][name]["domain"] == ""


def test_token_cookies_are_httponly_and_csrf_is_readable():
    settings = get_settings()
    jars = _parsed(_populated_response())

    assert jars[settings.access_cookie_name][settings.access_cookie_name]["httponly"] is True
    assert jars[settings.refresh_cookie_name][settings.refresh_cookie_name]["httponly"] is True
    assert jars[settings.csrf_cookie_name][settings.csrf_cookie_name]["httponly"] == ""


def test_samesite_comes_from_settings():
    settings = get_settings()
    jars = _parsed(_populated_response())

    for name in jars:
        assert jars[name][name]["samesite"].lower() == settings.cookie_samesite.lower()


def test_max_age_differs_between_access_and_refresh():
    settings = get_settings()
    jars = _parsed(_populated_response())

    assert jars[settings.access_cookie_name][settings.access_cookie_name]["max-age"] == str(
        _ACCESS_MAX_AGE
    )
    assert jars[settings.refresh_cookie_name][settings.refresh_cookie_name]["max-age"] == str(
        _REFRESH_MAX_AGE
    )
    assert jars[settings.csrf_cookie_name][settings.csrf_cookie_name]["max-age"] == str(
        _REFRESH_MAX_AGE
    )


def test_clear_auth_cookies_expires_all_three():
    response = Response()
    clear_auth_cookies(response)
    headers = _set_cookie_headers(response)

    assert len(headers) == _COOKIE_COUNT
    for header in headers:
        jar = SimpleCookie()
        jar.load(header)
        for name in jar:
            assert jar[name].value == ""
            assert jar[name]["max-age"] == "0"


def test_clear_auth_cookies_keeps_secure_and_path_attributes():
    response = Response()
    clear_auth_cookies(response)

    for header in _set_cookie_headers(response):
        jar = SimpleCookie()
        jar.load(header)
        for name in jar:
            assert jar[name]["secure"] is True
            assert jar[name]["path"] == "/"
            assert jar[name]["domain"] == ""
