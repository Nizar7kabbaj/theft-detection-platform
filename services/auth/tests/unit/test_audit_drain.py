from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.repositories.audit_outbox_repository import PendingEvent
from app.server.grpc_gen import audit_pb2 as pb
from app.services import audit_drain
from app.services.audit_drain import (
    SendOutcome,
    _next_attempt_at,
    _resolve,
    _send,
)

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
_MIN_JITTER = 0.8
_MAX_JITTER = 1.2
_FIRST_ATTEMPT_DELAY = 2.0


class FakeOutbox:
    def __init__(self) -> None:
        self.deferred: list[tuple[int, datetime]] = []
        self.released: list[int] = []
        self.buried: list[tuple[int, int]] = []

    async def defer(self, outbox_id: int, next_attempt_at: datetime) -> None:
        self.deferred.append((outbox_id, next_attempt_at))

    async def release(self, outbox_id: int) -> None:
        self.released.append(outbox_id)

    async def bury(self, pending: PendingEvent, last_status: int) -> None:
        self.buried.append((pending.id, last_status))


def _pending(attempts: int = 0) -> PendingEvent:
    return PendingEvent(
        id=7,
        event_id="44444444-4444-4444-4444-444444444444",
        event_bytes=b"",
        occurred_at=_NOW,
        attempts=attempts,
        created_at=_NOW,
    )


def test_first_backoff_sits_inside_jitter_band():
    delay = (_next_attempt_at(0) - datetime.now(UTC)).total_seconds()

    assert delay >= _FIRST_ATTEMPT_DELAY * _MIN_JITTER - 1
    assert delay <= _FIRST_ATTEMPT_DELAY * _MAX_JITTER + 1


def test_backoff_grows_with_attempts():
    early = (_next_attempt_at(1) - datetime.now(UTC)).total_seconds()
    later = (_next_attempt_at(5) - datetime.now(UTC)).total_seconds()

    assert later > early


def test_backoff_never_exceeds_the_ceiling_with_jitter():
    delay = (_next_attempt_at(1000) - datetime.now(UTC)).total_seconds()

    assert delay <= audit_drain._MAX_BACKOFF_SECONDS * _MAX_JITTER + 1


def test_ceiling_binds_before_the_exponent_cap():
    uncapped = audit_drain._BASE_BACKOFF_SECONDS * (2**audit_drain._MAX_BACKOFF_EXPONENT)

    assert uncapped > audit_drain._MAX_BACKOFF_SECONDS


def test_backoff_is_always_in_the_future():
    assert _next_attempt_at(0) > datetime.now(UTC)


async def test_unreachable_audit_defers():
    outbox = FakeOutbox()

    resolution = await _resolve(outbox, _pending(), SendOutcome(reachable=False, status=None))

    assert resolution == "deferred"
    assert len(outbox.deferred) == 1
    assert outbox.released == []


async def test_accepted_status_releases():
    outbox = FakeOutbox()

    resolution = await _resolve(
        outbox, _pending(), SendOutcome(reachable=True, status=pb.APPEND_STATUS_ACCEPTED)
    )

    assert resolution == "accepted"
    assert outbox.released == [7]


@pytest.mark.parametrize(
    "status",
    [pb.APPEND_STATUS_REJECTED, pb.APPEND_STATUS_SCHEMA_UNSUPPORTED],
)
async def test_terminal_status_buries_immediately(status: int):
    outbox = FakeOutbox()

    resolution = await _resolve(outbox, _pending(), SendOutcome(reachable=True, status=status))

    assert resolution == "buried"
    assert outbox.buried == [(7, status)]


async def test_unrecognised_status_defers_while_attempts_remain():
    outbox = FakeOutbox()

    resolution = await _resolve(
        outbox,
        _pending(attempts=0),
        SendOutcome(reachable=True, status=pb.APPEND_STATUS_RATE_LIMITED),
    )

    assert resolution == "deferred"
    assert outbox.buried == []


async def test_unrecognised_status_buries_on_final_attempt():
    outbox = FakeOutbox()
    attempts = audit_drain._MAX_UNKNOWN_STATUS_ATTEMPTS - 1

    resolution = await _resolve(
        outbox,
        _pending(attempts=attempts),
        SendOutcome(reachable=True, status=pb.APPEND_STATUS_RATE_LIMITED),
    )

    assert resolution == "buried"
    assert outbox.buried == [(7, pb.APPEND_STATUS_RATE_LIMITED)]


async def test_missing_status_is_recorded_as_zero_when_buried():
    outbox = FakeOutbox()

    await _resolve(
        outbox,
        _pending(attempts=audit_drain._MAX_UNKNOWN_STATUS_ATTEMPTS),
        SendOutcome(reachable=True, status=None),
    )

    assert outbox.buried == [(7, 0)]


async def test_send_reports_unreachable_when_no_stub_is_open(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(audit_drain, "audit_stub", lambda: None)

    outcome = await _send(_pending())

    assert outcome == SendOutcome(reachable=False, status=None)
