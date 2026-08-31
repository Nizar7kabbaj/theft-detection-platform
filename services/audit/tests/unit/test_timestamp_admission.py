from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.server import servicer as servicer_module
from app.server.grpc_gen import audit_pb2

pytestmark = pytest.mark.unit


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def test_an_unset_timestamp_reads_as_absent() -> None:
    request = audit_pb2.QueryEventsRequest()
    assert servicer_module._to_datetime(request, "from_time") is None


def test_a_set_timestamp_reads_as_a_datetime() -> None:
    request = audit_pb2.QueryEventsRequest()
    moment = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    request.from_time.FromDatetime(moment)
    assert servicer_module._to_datetime(request, "from_time") == moment


def test_an_epoch_timestamp_is_not_mistaken_for_absent() -> None:
    request = audit_pb2.QueryEventsRequest()
    request.from_time.FromDatetime(EPOCH)
    assert servicer_module._to_datetime(request, "from_time") == EPOCH


def test_an_epoch_timestamp_carries_the_utc_zone() -> None:
    request = audit_pb2.QueryEventsRequest()
    request.from_time.FromDatetime(EPOCH)
    assert servicer_module._to_datetime(request, "from_time").tzinfo == UTC


def test_clearing_a_timestamp_makes_it_absent_again() -> None:
    request = audit_pb2.QueryEventsRequest()
    request.from_time.FromDatetime(EPOCH)
    request.ClearField("from_time")
    assert servicer_module._to_datetime(request, "from_time") is None


def test_each_timestamp_field_is_read_independently() -> None:
    request = audit_pb2.QueryEventsRequest()
    request.to_time.FromDatetime(EPOCH)
    assert servicer_module._to_datetime(request, "from_time") is None
    assert servicer_module._to_datetime(request, "to_time") == EPOCH


def test_an_event_timestamp_is_read_the_same_way() -> None:
    event = audit_pb2.AuditEvent()
    assert servicer_module._to_datetime(event, "occurred_at") is None
    event.occurred_at.FromDatetime(EPOCH)
    assert servicer_module._to_datetime(event, "occurred_at") == EPOCH
