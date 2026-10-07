from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.core.errors import NotFoundError
from app.schemas.alert import Decision, DecisionChannel
from app.usecases.alert_usecase import AlertUseCase

OID = ObjectId("65f1a2b3c4d5e6f7a8b9c0d1")
OCCURRED_AT = datetime(2026, 10, 7, 11, 36, tzinfo=UTC)
DECIDED_AT = datetime(2026, 10, 7, 11, 43, tzinfo=UTC)


def _doc(
    decision: str = "DECISION_CONFIRMED",
    decided_by: str | None = "user-1",
    decided_at: datetime | None = DECIDED_AT,
) -> dict:
    return {
        "_id": OID,
        "alert_id": "cam-a-1-28409-3",
        "session_id": 1,
        "frame_index": 3,
        "occurred_at": OCCURRED_AT,
        "created_at": OCCURRED_AT,
        "camera_id": "cam-a",
        "severity": "SEVERITY_WARNING",
        "alert_type": "ALERT_TYPE_CONCEALMENT",
        "object": {"class_name": "bottle"},
        "decision": decision,
        "decided_at": decided_at,
        "decided_by": decided_by,
    }


@pytest.fixture(autouse=True)
def patch_cache(mocker):
    mocker.patch(
        "app.usecases.alert_usecase.invalidate_prefix",
        new=mocker.AsyncMock(return_value=None),
    )


@pytest.fixture
def parts(mocker):
    repo = mocker.AsyncMock()
    redis = mocker.AsyncMock()
    alert_client = mocker.AsyncMock()
    audit = mocker.AsyncMock()
    return AlertUseCase(repo, redis, alert_client, audit), repo, alert_client, audit


class TestDecide:
    async def test_a_change_is_audited_with_previous_and_channel(self, parts):
        usecase, repo, alert_client, audit = parts
        repo.decide.return_value = (_doc(), "DECISION_UNSURE")
        result = await usecase.decide(str(OID), Decision.DECISION_CONFIRMED, "user-1", "ws-admin")
        assert result.changed is True
        assert result.detail.decision == Decision.DECISION_CONFIRMED
        audit.emit_alert_decided.assert_awaited_once_with(
            alert_id=str(OID),
            actor_user_id="user-1",
            decision="DECISION_CONFIRMED",
            previous_decision="DECISION_UNSURE",
            channel="DECISION_CHANNEL_CONSOLE",
        )
        audit.emit_alert_acknowledged.assert_not_awaited()
        alert_client.notify_decision.assert_awaited_once_with(
            alert_id="cam-a-1-28409-3",
            decision="DECISION_CONFIRMED",
            decided_by="ws-admin",
            decided_at=DECIDED_AT,
        )

    async def test_telegram_mode_reaches_the_repository_and_the_audit(self, parts):
        usecase, repo, _alert_client, audit = parts
        repo.decide.return_value = (_doc(), "DECISION_UNSPECIFIED")
        await usecase.decide(
            str(OID),
            Decision.DECISION_CONFIRMED,
            "user-1",
            "ws-admin",
            channel=DecisionChannel.TELEGRAM,
            only_if_undecided=True,
        )
        repo.decide.assert_awaited_once_with(
            str(OID), "DECISION_CONFIRMED", "user-1", only_if_undecided=True
        )
        assert audit.emit_alert_decided.await_args.kwargs["channel"] == "DECISION_CHANNEL_TELEGRAM"

    async def test_no_change_emits_nothing(self, parts):
        usecase, repo, alert_client, audit = parts
        repo.decide.return_value = (_doc(), None)
        result = await usecase.decide(str(OID), Decision.DECISION_CONFIRMED, "user-1", "ws-admin")
        assert result.changed is False
        audit.emit_alert_decided.assert_not_awaited()
        alert_client.notify_decision.assert_not_awaited()

    async def test_clearing_sends_no_name_and_a_real_time(self, parts):
        usecase, repo, alert_client, _audit = parts
        repo.decide.return_value = (
            _doc("DECISION_UNSPECIFIED", None, None),
            "DECISION_CONFIRMED",
        )
        await usecase.decide(str(OID), Decision.DECISION_UNSPECIFIED, "user-1", "ws-admin")
        sent = alert_client.notify_decision.await_args.kwargs
        assert sent["decided_by"] == ""
        assert sent["decided_at"] is not None

    async def test_missing_alert_raises_not_found(self, parts):
        usecase, repo, _alert_client, _audit = parts
        repo.decide.return_value = (None, None)
        with pytest.raises(NotFoundError):
            await usecase.decide(str(OID), Decision.DECISION_CONFIRMED, "user-1", "ws-admin")
