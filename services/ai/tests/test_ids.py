import time
import uuid

from app.ids import new_alert_id

UUID_VERSION = 7


def test_ids_are_rfc9562_version_7():
    value = uuid.UUID(new_alert_id())
    assert value.version == UUID_VERSION
    assert value.variant == uuid.RFC_4122


def test_ids_carry_the_current_millisecond():
    before = time.time_ns() // 1_000_000
    value = uuid.UUID(new_alert_id())
    after = time.time_ns() // 1_000_000
    assert before <= value.int >> 80 <= after


def test_ids_sort_by_creation_time():
    first = new_alert_id()
    time.sleep(0.002)
    second = new_alert_id()
    assert first < second


def test_ten_thousand_ids_never_collide():
    assert len({new_alert_id() for _ in range(10_000)}) == 10_000
