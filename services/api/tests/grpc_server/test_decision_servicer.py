from datetime import UTC, datetime
from types import SimpleNamespace

import grpc
import pytest

from app.core.errors import AuthUnavailableError
from app.grpc_gen import audit_pb2, common_pb2, decision_pb2
from app.grpc_server import decision_servicer
from app.grpc_server.decision_servicer import AlertDecisionServicer
from app.schemas.alert import Decision, DecisionChannel
from app.services.auth_service import OperatorLookup

DECIDED_AT = datetime(2026, 10, 7, 11, 43, tzinfo=UTC)
OPERATOR = OperatorLookup(
    found=True,
    user_id="user-1",
    username="ws-admin",
    roles=frozenset({"operator"}),
    active=True,
)


class AbortedError(Exception):
    def __init__(self, code: grpc.StatusCode) -> None:
        super().__init__(code)
        self.code = code


@pytest.fixture
def context(mocker):
    async def abort(code, _details):
        raise AbortedError(code)

    ctx = mocker.MagicMock()
    ctx.abort = abort
    return ctx


@pytest.fixture
def caller(mocker):
    return mocker.patch.object(
        decision_servicer, "peer_service", return_value=common_pb2.SOURCE_SERVICE_NOTIFICATION
    )


@pytest.fixture
def parts(mocker, caller):
    repo = mocker.AsyncMock()
    repo.get_by_alert_id.return_value = {"_id": "65f1a2b3c4d5e6f7a8b9c0d1"}
    audit = mocker.AsyncMock()
    usecase = mocker.AsyncMock()
    usecase.decide.return_value = SimpleNamespace(
        changed=True,
        detail=SimpleNamespace(
            decision=Decision.DECISION_CONFIRMED, decided_at=DECIDED_AT, decided_by="user-1"
        ),
    )
    mocker.patch.object(decision_servicer, "AlertRepository", return_value=repo)
    mocker.patch.object(decision_servicer, "AuditClient", return_value=audit)
    mocker.patch.object(decision_servicer, "AlertUseCase", return_value=usecase)
    auth = mocker.AsyncMock()
    auth.lookup_operator.return_value = OPERATOR
    servicer = AlertDecisionServicer(
        mocker.MagicMock(), mocker.AsyncMock(), mocker.AsyncMock(), auth
    )
    return servicer, repo, audit, usecase, auth


def _request(decision: int = common_pb2.DECISION_CONFIRMED) -> decision_pb2.DecideAlertRequest:
    return decision_pb2.DecideAlertRequest(
        alert_id="cam-a-1-28409-3", decision=decision, telegram_user_id=777
    )


class TestDecideAlert:
    async def test_only_notification_may_call(self, parts, context, caller):
        servicer, *_ = parts
        caller.return_value = common_pb2.SOURCE_SERVICE_CAMERA
        with pytest.raises(AbortedError) as caught:
            await servicer.DecideAlert(_request(), context)
        assert caught.value.code == grpc.StatusCode.PERMISSION_DENIED

    async def test_an_unspecified_decision_is_rejected(self, parts, context):
        servicer, *_ = parts
        with pytest.raises(AbortedError) as caught:
            await servicer.DecideAlert(_request(common_pb2.DECISION_UNSPECIFIED), context)
        assert caught.value.code == grpc.StatusCode.INVALID_ARGUMENT

    async def test_an_unlinked_account_decides_nothing(self, parts, context):
        servicer, _repo, _audit, usecase, auth = parts
        auth.lookup_operator.return_value = OperatorLookup(
            found=False, user_id="", username="", roles=frozenset(), active=False
        )
        reply = await servicer.DecideAlert(_request(), context)
        assert reply.outcome == decision_pb2.DECIDE_OUTCOME_OPERATOR_UNKNOWN
        usecase.decide.assert_not_awaited()

    @pytest.mark.parametrize(
        ("roles", "active"),
        [(frozenset({"viewer"}), True), (frozenset({"operator"}), False)],
    )
    async def test_no_permission_is_refused_and_audited(self, parts, context, roles, active):
        servicer, _repo, audit, usecase, auth = parts
        auth.lookup_operator.return_value = OperatorLookup(
            found=True, user_id="user-2", username="viewer", roles=roles, active=active
        )
        reply = await servicer.DecideAlert(_request(), context)
        assert reply.outcome == decision_pb2.DECIDE_OUTCOME_OPERATOR_FORBIDDEN
        usecase.decide.assert_not_awaited()
        denied = audit.emit_authorization_denied.await_args.kwargs
        assert denied["subject_id"] == "user-2"
        assert denied["channel"] == audit_pb2.AUTHORIZATION_CHANNEL_TELEGRAM
        assert denied["required_permission"] == "alert:acknowledge"

    async def test_a_missing_alert_is_reported(self, parts, context):
        servicer, repo, _audit, usecase, _auth = parts
        repo.get_by_alert_id.return_value = None
        reply = await servicer.DecideAlert(_request(), context)
        assert reply.outcome == decision_pb2.DECIDE_OUTCOME_ALERT_NOT_FOUND
        usecase.decide.assert_not_awaited()

    async def test_a_press_decides_once_in_telegram_mode(self, parts, context):
        servicer, _repo, _audit, usecase, _auth = parts
        reply = await servicer.DecideAlert(_request(), context)
        assert reply.outcome == decision_pb2.DECIDE_OUTCOME_DECIDED
        assert reply.decision == common_pb2.DECISION_CONFIRMED
        assert reply.decided_by == "ws-admin"
        assert reply.decided_at.ToDatetime(tzinfo=UTC) == DECIDED_AT
        kwargs = usecase.decide.await_args.kwargs
        assert kwargs["channel"] is DecisionChannel.TELEGRAM
        assert kwargs["only_if_undecided"] is True

    async def test_already_decided_names_the_original_decider(self, parts, context):
        servicer, _repo, _audit, usecase, auth = parts
        usecase.decide.return_value = SimpleNamespace(
            changed=False,
            detail=SimpleNamespace(
                decision=Decision.DECISION_CONFIRMED, decided_at=DECIDED_AT, decided_by="user-9"
            ),
        )
        auth.lookup_operator.side_effect = [
            OPERATOR,
            OperatorLookup(
                found=True,
                user_id="user-9",
                username="manager",
                roles=frozenset({"admin"}),
                active=True,
            ),
        ]
        reply = await servicer.DecideAlert(_request(common_pb2.DECISION_DISMISSED), context)
        assert reply.outcome == decision_pb2.DECIDE_OUTCOME_ALREADY_DECIDED
        assert reply.decision == common_pb2.DECISION_CONFIRMED
        assert reply.decided_by == "manager"

    async def test_auth_down_is_unavailable(self, parts, context):
        servicer, _repo, _audit, _usecase, auth = parts
        auth.lookup_operator.side_effect = AuthUnavailableError("auth service unavailable")
        with pytest.raises(AbortedError) as caught:
            await servicer.DecideAlert(_request(), context)
        assert caught.value.code == grpc.StatusCode.UNAVAILABLE
