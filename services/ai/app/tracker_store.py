from __future__ import annotations
import threading
import numpy as np
import redis


_BBOX_LEN = 4
_KP_SHAPE = (17, 3)
_KP_LEN = _KP_SHAPE[0] * _KP_SHAPE[1]



class TrackerStore:
    def __init__(self, redis_url: str, window: int, ttl_seconds: int) -> None:
        self._redis_url = redis_url
        self._window = window
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._client: redis.Redis | None = None
    def _get_client(self) -> redis.Redis:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    pool = redis.ConnectionPool.from_url(
                        self._redis_url,
                        max_connections=16,
                    )
                    self._client = redis.Redis(connection_pool=pool)
        return self._client

    @staticmethod
    def _key(camera_id: str, track_id: int) -> str:
        return f"ai:track:{camera_id}:{track_id}"
    def append(
        self,
        camera_id: str,
        track_id: int,
        frame_index: int,
        bbox_xyxy: tuple[float, float, float, float],
        keypoints: np.ndarray,
    ) -> None:
        bbox = np.asarray(bbox_xyxy, dtype=np.float32)
        kp = np.asarray(keypoints, dtype=np.float32)
        if bbox.shape[0] != _BBOX_LEN or kp.shape != _KP_SHAPE:
            return
        key = self._key(camera_id, track_id)
        client = self._get_client()
        pipe = client.pipeline(transaction=False)
        pipe.xadd(
            key,
            {
                "frame_index": frame_index,
                "bbox": bbox.tobytes(),
                "kp": kp.tobytes(),
            },
            maxlen=self._window,
            approximate=True,
        )
        pipe.expire(key, self._ttl)
        pipe.execute()
    def read_window(
        self,
        camera_id: str,
        track_id: int,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        key = self._key(camera_id, track_id)
        client = self._get_client()
        entries = client.xrange(key, count=self._window)
        out: list[tuple[np.ndarray, np.ndarray]] = []
        for _entry_id, fields in entries:
            raw_bbox = fields.get(b"bbox")
            raw_kp = fields.get(b"kp")
            if raw_bbox is None or raw_kp is None:
                continue
            bbox = np.frombuffer(raw_bbox, dtype=np.float32)
            kp = np.frombuffer(raw_kp, dtype=np.float32)
            if bbox.shape[0] != _BBOX_LEN or kp.shape[0] != _KP_LEN:
                continue
            out.append((bbox.copy(), kp.reshape(_KP_SHAPE).copy()))
        return out
    def drop(self, camera_id: str, track_id: int) -> None:
        key = self._key(camera_id, track_id)
        client = self._get_client()
        client.delete(key)
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
