from __future__ import annotations

import pytest

from app.core.telegram_link import hash_link_token, is_well_formed_link_token, new_link_token


def test_new_tokens_are_well_formed_and_unique() -> None:
    first, second = new_link_token(), new_link_token()
    assert len(first) == 43
    assert is_well_formed_link_token(first)
    assert first != second


def test_hash_is_stable_and_hides_the_token() -> None:
    token = new_link_token()
    digest = hash_link_token(token)
    assert digest == hash_link_token(token)
    assert len(digest) == 64
    assert token not in digest


@pytest.mark.parametrize(
    "token",
    ["", "short", "a" * 42, "a" * 44, "a" * 42 + "!", "a" * 42 + "é", "a" * 42 + " "],
)
def test_anything_but_43_url_safe_characters_is_rejected(token: str) -> None:
    assert is_well_formed_link_token(token) is False
