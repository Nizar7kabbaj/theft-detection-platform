from __future__ import annotations

import logging
from datetime import datetime

import grpc
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis
from typing_extensions import override

from app.core.errors import AuthUnavailableError, NotFoundError
from app.core.permissions import Permission, resolve_permissions
from app.grpc_gen import audit_pb2, common_pb2, decision_pb2, decision_pb2_grpc
from app.grpc_server.interceptors import peer_service
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import Decision, DecisionChannel
from app.services.alert_service import AlertClient
from app.services.audit_service import AuditClient
from app.services.auth_service import AuthClient
from app.usecases.alert_usecase import AlertUseCase

logger = logging.getLogger(__name__)

_DECISIONS = {
    common_pb2.DECISION_CONFIRMED: Decision.DECISION_CONFIRMED,
    common_pb2.DECISION_DISMISSED: Decision.DECISION_DISMISSED,
    common_pb2.DECISION_UNSURE: Decision.DECISION_UNSURE,
}
_REQUIRED = Permission.ALERT_ACKNOWLEDGE


def _reply(
    outcome: int,
    decision: Decision = Decision.DECISION_UNSPECIFIED,
    decided_by: str = "",
    decided_at: datetime | None = None,
) -> decision_pb2.DecideAlertReply:
    reply = decision_pb2.DecideAlertReply(
        outcome=outcome,
        decision=common_pb2.Decision.Value(decision.value),
        decided_by=decided_by,
    )
    if decided_at is not None:
        reply.decided_at.FromDatetime(decided_at)
    return reply


class AlertDecisionServicer(decision_pb2_grpc.AlertDecisionServiceServicer):
    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        redis: Redis,
        alert_client: AlertClient,
        auth_client: AuthClient,
    ) -> None:
        self._database = database
        self._redis = redis
        self._alert_client = alert_client
        self._auth = auth_client

    async def _username(self, user_id: str | None) -> str:
        if not user_id:
            return ""
        try:
            found = await self._auth.lookup_operator(user_id=user_id)
        except (AuthUnavailableError, grpc.aio.AioRpcError):
            return ""
        return found.username if found.found else ""

    @override
    async def DecideAlert(
        self,
        request: decision_pb2.DecideAlertRequest,
        context: grpc.aio.ServicerContext,
    ) -> decision_pb2.DecideAlertReply:
        caller = peer_service()
        if caller != common_pb2.SOURCE_SERVICE_NOTIFICATION:
            logger.warning("decide alert refused for caller %d", caller)
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "caller is not allowed")
        decision = _DECISIONS.get(request.decision)
        if decision is None or not request.alert_id or request.telegram_user_id <= 0:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "alert_id, decision and telegram_user_id required",
            )
        try:
            operator = await self._auth.lookup_operator(telegram_user_id=request.telegram_user_id)
        except AuthUnavailableError:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "operator lookup unavailable")
        if not operator.found:
            logger.info("telegram decision from unlinked account alert=%s", request.alert_id)
            return _reply(decision_pb2.DECIDE_OUTCOME_OPERATOR_UNKNOWN)
        repo = AlertRepository(self._database.alerts)
        audit = AuditClient(self._database)
        if not operator.active or _REQUIRED not in resolve_permissions(operator.roles):
            await audit.emit_authorization_denied(
                subject_id=operator.user_id,
                required_permission=_REQUIRED.value,
                channel=audit_pb2.AUTHORIZATION_CHANNEL_TELEGRAM,
                method="DecideAlert",
                path="telegram:decision",
                roles=operator.roles,
            )
            logger.info("telegram decision refused user_id=%s", operator.user_id)
            return _reply(decision_pb2.DECIDE_OUTCOME_OPERATOR_FORBIDDEN)
        doc = await repo.get_by_alert_id(request.alert_id)
        if doc is None:
            return _reply(decision_pb2.DECIDE_OUTCOME_ALERT_NOT_FOUND)
        usecase = AlertUseCase(repo, self._redis, self._alert_client, audit)
        try:
            result = await usecase.decide(
                str(doc["_id"]),
                decision,
                operator.user_id,
                operator.username,
                channel=DecisionChannel.TELEGRAM,
                only_if_undecided=True,
            )
        except NotFoundError:
            return _reply(decision_pb2.DECIDE_OUTCOME_ALERT_NOT_FOUND)
        detail = result.detail
        if result.changed:
            logger.info(
                "telegram decision recorded alert=%s decision=%s user_id=%s",
                request.alert_id,
                detail.decision.value,
                operator.user_id,
            )
            return _reply(
                decision_pb2.DECIDE_OUTCOME_DECIDED,
                detail.decision,
                operator.username,
                detail.decided_at,
            )
        return _reply(
            decision_pb2.DECIDE_OUTCOME_ALREADY_DECIDED,
            detail.decision,
            await self._username(detail.decided_by),
            detail.decided_at,
        )
