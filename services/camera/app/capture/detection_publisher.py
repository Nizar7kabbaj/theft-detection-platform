from __future__ import annotations

import json
import logging

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from app.grpc_gen import inference_pb2

logger = logging.getLogger(__name__)


class DetectionPublisher:
    def __init__(
        self,
        redis_url: str,
        stream_key: str,
        maxlen: int,
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._maxlen = maxlen
        self._connection_kwargs = dict(connection_kwargs or {})
        self._client: aioredis.Redis | None = None
        self._published_total = 0
        self._failed_total = 0

    @property
    def counters(self) -> dict[str, int]:
        return {
            "published_total": self._published_total,
            "failed_total": self._failed_total,
        }

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            pool = aioredis.ConnectionPool.from_url(
                self._redis_url,
                max_connections=4,
                **self._connection_kwargs,
            )
            self._client = aioredis.Redis(connection_pool=pool)
        return self._client

    async def publish(
        self,
        detection: inference_pb2.Detection,
        session_id: int,
        frame_index: int,
        timestamp_unix: float,
    ) -> None:
        body = json.dumps(
            {
                "session_id": session_id,
                "frame_index": frame_index,
                "timestamp_unix": timestamp_unix,
                "frame_width": detection.frame_width,
                "frame_height": detection.frame_height,
                "detection_present": detection.detection_present,
                "persons": [
                    {
                        "track_id": person.track_id,
                        "bbox": {
                            "x1": person.bbox.x1,
                            "y1": person.bbox.y1,
                            "x2": person.bbox.x2,
                            "y2": person.bbox.y2,
                        },
                        "keypoints": [
                            {"x": kp.x, "y": kp.y, "confidence": kp.confidence}
                            for kp in person.keypoints
                        ],
                        "score": person.score,
                        "inference_state": inference_pb2.InferenceState.Name(
                            person.inference_state
                        ),
                    }
                    for person in detection.persons
                ],
                "objects": [
                    {
                        "track_id": obj.track_id,
                        "class_name": obj.class_name,
                        "bbox": {
                            "x1": obj.bbox.x1,
                            "y1": obj.bbox.y1,
                            "x2": obj.bbox.x2,
                            "y2": obj.bbox.y2,
                        },
                        "confidence": obj.confidence,
                    }
                    for obj in detection.objects
                ],
            }
        )
        try:
            client = self._get_client()
            await client.xadd(
                self._stream_key,
                {"body": body},
                maxlen=self._maxlen,
                approximate=True,
            )
            self._published_total += 1
        except RedisError as exc:
            self._failed_total += 1
            logger.warning("detection publish failed error=%s", type(exc).__name__)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
