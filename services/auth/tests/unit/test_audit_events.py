from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.roles import Role
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import common_pb2
from app.services import audit_service
from app.services.audit_service import (
    admin_session_revoked,
    login_failure,
    login_success,
    refresh_reuse_detected,
    session_ended,
    throttle_triggered,
    token_refreshed,
)

_SUBJECT = "11111111-1111-1111-1111-111111111111"
_SESSION = "22222222-2222-2222-2222-222222222222"
_FAMILY = "33333333-3333-3333-3333-333333333333"
_SCHEMA_VERSION = 1
_ATTEMPT_COUNT = 4
_THRESHOLD = 5
_WINDOW_SECONDS = 900


def _decode(event_bytes: bytes) -> pb.AuditEvent:
    event = pb.AuditEvent()
    event.ParseFromString(event_bytes)
    return event


def test_login_success_carries_subject_session_and_client():
    prepared = login_success(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        roles=["operator"],
        source_ip="10.0.0.4",
        user_agent="harness",
    )
    event = _decode(prepared.event_bytes)

    assert event.schema_version == _SCHEMA_VERSION
    assert event.source_service == common_pb2.SOURCE_SERVICE_AUTH
    assert event.actor == _SUBJECT
    assert event.severity == common_pb2.SEVERITY_INFO
    assert event.login_success.subject_id == _SUBJECT
    assert event.login_success.session_id == _SESSION
    assert event.login_success.client.source_ip == "10.0.0.4"
    assert event.login_success.client.user_agent == "harness"


def test_prepared_event_id_matches_serialized_event():
    prepared = login_success(
        subject_id=_SUBJECT, session_id=_SESSION, roles=[], source_ip="", user_agent=""
    )

    assert _decode(prepared.event_bytes).event_id == prepared.event_id


def test_occurred_at_is_timezone_aware_and_matches_payload():
    prepared = login_success(
        subject_id=_SUBJECT, session_id=_SESSION, roles=[], source_ip="", user_agent=""
    )
    event = _decode(prepared.event_bytes)

    assert prepared.occurred_at.tzinfo is not None
    assert event.occurred_at.ToDatetime(tzinfo=UTC) == prepared.occurred_at


def test_event_ids_are_unique_per_call():
    first = login_success(
        subject_id=_SUBJECT, session_id=_SESSION, roles=[], source_ip="", user_agent=""
    )
    second = login_success(
        subject_id=_SUBJECT, session_id=_SESSION, roles=[], source_ip="", user_agent=""
    )

    assert first.event_id != second.event_id


def test_human_roles_map_to_enum_values():
    prepared = login_success(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        roles=["admin", "operator", "viewer", "ml_engineer", "compliance"],
        source_ip="",
        user_agent="",
    )

    assert list(_decode(prepared.event_bytes).login_success.roles) == [
        common_pb2.ROLE_ADMIN,
        common_pb2.ROLE_OPERATOR,
        common_pb2.ROLE_VIEWER,
        common_pb2.ROLE_ML_ENGINEER,
        common_pb2.ROLE_COMPLIANCE,
    ]


def test_detector_role_has_no_audit_enum_and_is_dropped():
    assert not hasattr(common_pb2, "ROLE_DETECTOR")

    prepared = login_success(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        roles=["detector", "operator"],
        source_ip="",
        user_agent="",
    )

    assert list(_decode(prepared.event_bytes).login_success.roles) == [common_pb2.ROLE_OPERATOR]


def test_role_map_covers_every_role_with_an_audit_enum():
    mapped = set(audit_service._ROLE_BY_NAME)
    unmapped = {str(role) for role in Role} - mapped

    assert unmapped == {"detector"}


def test_unknown_role_name_is_dropped():
    prepared = login_success(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        roles=["not-a-role"],
        source_ip="",
        user_agent="",
    )

    assert list(_decode(prepared.event_bytes).login_success.roles) == []


def test_login_failure_pseudonymizes_username_and_omits_actor():
    prepared = login_failure(
        username="operator",
        reason=pb.AUTH_FAILURE_REASON_BAD_CREDENTIAL,
        attempt_count=_ATTEMPT_COUNT,
        source_ip="10.0.0.4",
        user_agent="harness",
    )
    event = _decode(prepared.event_bytes)

    assert event.actor == ""
    assert event.severity == common_pb2.SEVERITY_WARNING
    assert event.login_failure.subject_hmac
    assert b"operator" not in prepared.event_bytes
    assert event.login_failure.reason == pb.AUTH_FAILURE_REASON_BAD_CREDENTIAL
    assert event.login_failure.attempt_count == _ATTEMPT_COUNT


def test_login_failure_returns_none_when_pseudonym_key_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AUTH_PSEUDONYM_KEY_FILE", "/nonexistent/pseudonym_key")
    from app.core.config import get_settings
    from app.core.pseudonym import reset_cache

    get_settings.cache_clear()
    reset_cache()

    assert (
        login_failure(
            username="operator",
            reason=pb.AUTH_FAILURE_REASON_BAD_CREDENTIAL,
            attempt_count=1,
            source_ip="",
            user_agent="",
        )
        is None
    )
    reset_cache()


def test_session_ended_carries_kind():
    prepared = session_ended(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        kind=pb.SESSION_END_KIND_USER_LOGOUT,
        source_ip="",
        user_agent="",
    )
    event = _decode(prepared.event_bytes)

    assert event.session_ended.kind == pb.SESSION_END_KIND_USER_LOGOUT
    assert event.session_ended.session_id == _SESSION


def test_token_refreshed_carries_family():
    prepared = token_refreshed(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        family_id=_FAMILY,
        source_ip="",
        user_agent="",
    )
    event = _decode(prepared.event_bytes)

    assert event.severity == common_pb2.SEVERITY_INFO
    assert event.token_refreshed.family_id == _FAMILY


def test_refresh_reuse_is_critical():
    prepared = refresh_reuse_detected(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        family_id=_FAMILY,
        source_ip="",
        user_agent="",
    )
    event = _decode(prepared.event_bytes)

    assert event.severity == common_pb2.SEVERITY_CRITICAL
    assert event.refresh_token_reuse_detected.family_id == _FAMILY


def test_throttle_triggered_reports_counts_and_bucket():
    prepared = throttle_triggered(
        username="operator",
        observed_count=_THRESHOLD,
        threshold=_THRESHOLD,
        window_seconds=_WINDOW_SECONDS,
    )
    event = _decode(prepared.event_bytes)

    assert event.severity == common_pb2.SEVERITY_CRITICAL
    assert event.auth_throttle_triggered.bucket == pb.THROTTLE_BUCKET_ACCOUNT
    assert event.auth_throttle_triggered.threshold == _THRESHOLD
    assert event.auth_throttle_triggered.window_seconds == _WINDOW_SECONDS
    assert b"operator" not in prepared.event_bytes


def test_throttle_returns_none_when_pseudonym_key_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AUTH_PSEUDONYM_KEY_FILE", "/nonexistent/pseudonym_key")
    from app.core.config import get_settings
    from app.core.pseudonym import reset_cache

    get_settings.cache_clear()
    reset_cache()

    assert (
        throttle_triggered(
            username="operator",
            observed_count=1,
            threshold=_THRESHOLD,
            window_seconds=_WINDOW_SECONDS,
        )
        is None
    )
    reset_cache()


def test_admin_session_revoked_records_actor_and_target():
    prepared = admin_session_revoked(actor_user_id=_SUBJECT, session_id=_SESSION)
    event = _decode(prepared.event_bytes)

    assert event.actor == _SUBJECT
    assert event.severity == common_pb2.SEVERITY_NOTICE
    assert event.admin_action.action == pb.ADMIN_ACTION_KIND_REVOKE_SESSION
    assert event.admin_action.target_kind == pb.ADMIN_TARGET_KIND_SESSION
    assert event.admin_action.target_id == _SESSION


def test_serialization_is_deterministic_for_identical_events():
    prepared = login_success(
        subject_id=_SUBJECT,
        session_id=_SESSION,
        roles=["operator"],
        source_ip="10.0.0.4",
        user_agent="harness",
    )
    event = _decode(prepared.event_bytes)

    assert event.SerializeToString(deterministic=True) == prepared.event_bytes


def test_occurred_at_is_recent():
    prepared = admin_session_revoked(actor_user_id=_SUBJECT, session_id=_SESSION)
    drift = abs((datetime.now(UTC) - prepared.occurred_at).total_seconds())

    assert drift < 5
