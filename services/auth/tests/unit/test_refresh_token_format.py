from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.v1.auth import (
    _MAX_SUCCESSOR_HOPS,
    _build_refresh_token,
    _resolve_presented_refresh,
    _split_refresh_token,
)
from app.db.models.refresh_token import RefreshToken

_GRACE_SECONDS = 30
_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


class FakeRefreshTokenRepository:
    def __init__(self, tokens: list[RefreshToken] | None = None) -> None:
        self._by_jti = {token.jti: token for token in tokens or []}
        self.lookups: list[str] = []

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        self.lookups.append(jti)
        return self._by_jti.get(jti)


def _token(
    jti: str,
    *,
    revoked: bool = False,
    rotated_at: datetime | None = None,
    replaced_by: str | None = None,
    expires_at: datetime | None = None,
) -> RefreshToken:
    return RefreshToken(
        jti=jti,
        family_id="family",
        session_id="session",
        token_hash=f"hash-{jti}",
        revoked=revoked,
        rotated_at=rotated_at,
        replaced_by=replaced_by,
        expires_at=expires_at or (_NOW + timedelta(days=1)),
    )


def test_build_and_split_round_trip():
    raw = _build_refresh_token("jti-value", "secret-value")

    assert raw == "jti-value.secret-value"
    assert _split_refresh_token(raw) == ("jti-value", "secret-value")


def test_split_keeps_dots_inside_secret():
    assert _split_refresh_token("jti.secret.with.dots") == ("jti", "secret.with.dots")


@pytest.mark.parametrize(
    "raw",
    ["", "no-separator", ".secret-value", "jti-value.", ".", "..."],
)
def test_split_rejects_malformed_tokens(raw: str):
    assert _split_refresh_token(raw) is None


async def test_live_token_is_returned_unchanged():
    stored = _token("root")
    repo = FakeRefreshTokenRepository()

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is stored
    assert repo.lookups == []


async def test_revoked_token_without_rotation_is_rejected():
    stored = _token("root", revoked=True, rotated_at=None)

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=FakeRefreshTokenRepository(),
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None


async def test_rotation_outside_grace_window_is_rejected():
    stored = _token(
        "root",
        revoked=True,
        rotated_at=_NOW - timedelta(seconds=_GRACE_SECONDS + 1),
        replaced_by="next",
    )
    repo = FakeRefreshTokenRepository([_token("next")])

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None
    assert repo.lookups == []


async def test_rotation_inside_grace_window_returns_successor():
    successor = _token("next")
    stored = _token(
        "root",
        revoked=True,
        rotated_at=_NOW - timedelta(seconds=5),
        replaced_by="next",
    )
    repo = FakeRefreshTokenRepository([successor])

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is successor


async def test_grace_boundary_is_inclusive():
    successor = _token("next")
    stored = _token(
        "root",
        revoked=True,
        rotated_at=_NOW - timedelta(seconds=_GRACE_SECONDS),
        replaced_by="next",
    )
    repo = FakeRefreshTokenRepository([successor])

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is successor


async def test_missing_successor_pointer_is_rejected():
    stored = _token("root", revoked=True, rotated_at=_NOW, replaced_by=None)

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=FakeRefreshTokenRepository(),
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None


async def test_successor_absent_from_store_is_rejected():
    stored = _token("root", revoked=True, rotated_at=_NOW, replaced_by="gone")

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=FakeRefreshTokenRepository(),
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None


async def test_expired_successor_is_rejected():
    successor = _token("next", expires_at=_NOW - timedelta(seconds=1))
    stored = _token("root", revoked=True, rotated_at=_NOW, replaced_by="next")

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=FakeRefreshTokenRepository([successor]),
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None


async def test_chain_walks_past_revoked_successors():
    stored = _token("root", revoked=True, rotated_at=_NOW, replaced_by="second")
    second = _token("second", revoked=True, rotated_at=_NOW, replaced_by="third")
    third = _token("third")
    repo = FakeRefreshTokenRepository([second, third])

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is third
    assert repo.lookups == ["second", "third"]


async def test_chain_longer_than_hop_limit_is_rejected():
    chain = [
        _token(f"hop{index}", revoked=True, rotated_at=_NOW, replaced_by=f"hop{index + 1}")
        for index in range(1, _MAX_SUCCESSOR_HOPS + 2)
    ]
    stored = _token("root", revoked=True, rotated_at=_NOW, replaced_by="hop1")
    repo = FakeRefreshTokenRepository(chain)

    resolved = await _resolve_presented_refresh(
        stored=stored,
        refresh_tokens=repo,
        now=_NOW,
        grace_seconds=_GRACE_SECONDS,
    )

    assert resolved is None
    assert len(repo.lookups) == _MAX_SUCCESSOR_HOPS
