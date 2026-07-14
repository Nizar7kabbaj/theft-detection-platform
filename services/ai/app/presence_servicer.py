from __future__ import annotations
import logging
from opentelemetry import trace
from app.grpc_gen import presence_pb2, presence_pb2_grpc
from app.observability import get_presence_events_counter


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


_KIND_TO_GAUGE = {
    presence_pb2.PRESENCE_EVENT_KIND_PERSON_ENTERED: 1,
    presence_pb2.PRESENCE_EVENT_KIND_PERSON_LEFT: 0,
}


class PresenceServicer(presence_pb2_grpc.PresenceServiceServicer):
    def __init__(self) -> None:
        self._events_counter = get_presence_events_counter()
        self._state_by_camera: dict[str, int] = {}
        self._seen_by_camera: dict[str, set[str]] = {}
    def presence_value(self, camera_id: str) -> int:
        return self._state_by_camera.get(camera_id, 0)
    def cameras(self) -> list[str]:
        return list(self._state_by_camera.keys())
    async def StreamPresence(self, request_iterator, context):
        async for event in request_iterator:
            yield self._handle(event)
    def _handle(self, event: presence_pb2.PresenceEvent) -> presence_pb2.PresenceAck:
        with tracer.start_as_current_span("presence.handle_event") as span:
            span.set_attribute("camera_id", event.camera_id)
            span.set_attribute("event_id", event.event_id)
            span.set_attribute("kind", presence_pb2.PresenceEventKind.Name(event.kind))
            seen = self._seen_by_camera.setdefault(event.camera_id, set())
            if event.event_id in seen:
                return presence_pb2.PresenceAck(
                    event_id=event.event_id,
                    status=presence_pb2.ACK_STATUS_DROPPED_DUPLICATE,
                )
            seen.add(event.event_id)
            gauge_value = _KIND_TO_GAUGE.get(event.kind)
            if gauge_value is None:
                return presence_pb2.PresenceAck(
                    event_id=event.event_id,
                    status=presence_pb2.ACK_STATUS_DROPPED_STALE,
                )
            self._state_by_camera[event.camera_id] = gauge_value
            self._events_counter.add(1, {"camera_id": event.camera_id})
            logger.info(
                "presence event camera=%s kind=%s",
                event.camera_id,
                presence_pb2.PresenceEventKind.Name(event.kind),
            )
            return presence_pb2.PresenceAck(
                event_id=event.event_id,
                status=presence_pb2.ACK_STATUS_ACCEPTED,
            )
