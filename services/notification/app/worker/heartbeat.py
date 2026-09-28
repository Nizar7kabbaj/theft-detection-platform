from typing import Any

from celery import bootsteps
from celery.beat import PersistentScheduler

from app.shared.config import settings

INTERVAL_SECONDS = 10.0


def _touch() -> None:
    settings.HEARTBEAT_FILE.touch()


class HeartbeatStep(bootsteps.StartStopStep):
    requires = frozenset({"celery.worker.consumer.tasks:Tasks"})

    def __init__(self, parent: Any, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self._timer_ref: Any = None

    def start(self, parent: Any) -> None:
        _touch()
        self._timer_ref = parent.timer.call_repeatedly(INTERVAL_SECONDS, _touch, priority=10)

    def stop(self, parent: Any) -> None:
        if self._timer_ref is not None:
            self._timer_ref.cancel()
            self._timer_ref = None


class HeartbeatScheduler(PersistentScheduler):
    def tick(self, *args: Any, **kwargs: Any) -> float:
        _touch()
        return super().tick(*args, **kwargs)
