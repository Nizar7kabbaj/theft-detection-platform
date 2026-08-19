from __future__ import annotations

import logging
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis

from app.core.cache import get_or_set, invalidate
from app.core.errors import ConflictError, NotFoundError
from app.repositories.camera_repository import CameraRepository
from app.schemas.camera import CameraCreate, CameraHealthView, CameraResponse
from app.services.camera_health import read_health

logger = logging.getLogger(__name__)


class CameraUseCase:
    LIST_KEY = "cache:cameras:list"
    TTL = 300

    def __init__(self, repo: CameraRepository, redis: Redis, stream: Redis) -> None:
        self._repo = repo
        self._redis = redis
        self._stream = stream

    async def _with_health(self, camera: CameraResponse) -> CameraResponse:
        health = await read_health(self._stream, camera.camera_id)
        last_frame_at = (
            datetime.fromtimestamp(health.last_frame_at, tz=UTC)
            if health.last_frame_at is not None
            else None
        )
        view = CameraHealthView(
            state=health.state,
            last_frame_at=last_frame_at,
            age_seconds=health.age_seconds,
        )
        return camera.model_copy(update={"health": view})

    @staticmethod
    def _item_key(camera_id: str) -> str:
        return f"cache:cameras:{camera_id}"

    async def _publish(self, event: str, response: CameraResponse) -> None:
        try:
            payload = response.model_dump_json(by_alias=True)
            await self._redis.publish(f"cameras:{event}", payload)
        except Exception as exc:
            logger.warning("pubsub publish failed event=%s: %s", event, exc)

    async def create(self, payload: CameraCreate) -> CameraResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(UTC)
        try:
            created = await self._repo.create(doc)
        except DuplicateKeyError as exc:
            raise ConflictError(f"camera with name {payload.name} already exists") from exc
        await invalidate(self._redis, self.LIST_KEY)
        response = CameraResponse.model_validate(created)
        await self._publish("created", response)
        return response

    async def list(self) -> list[CameraResponse]:
        async def loader() -> list[dict]:
            docs = await self._repo.list(limit=200)
            return [CameraResponse.model_validate(d).model_dump(mode="json") for d in docs]

        cached = await get_or_set(self._redis, self.LIST_KEY, self.TTL, loader)
        cameras = [CameraResponse.model_validate(item) for item in cached]
        return [await self._with_health(c) for c in cameras]

    async def get(self, camera_id: str) -> CameraResponse:
        async def loader() -> dict:
            doc = await self._repo.get(camera_id)
            if doc is None:
                raise NotFoundError(f"camera {camera_id} not found")
            return CameraResponse.model_validate(doc).model_dump(mode="json")

        cached = await get_or_set(self._redis, self._item_key(camera_id), self.TTL, loader)
        return await self._with_health(CameraResponse.model_validate(cached))

    async def delete(self, camera_id: str) -> None:
        doc = await self._repo.get(camera_id)
        if doc is None:
            raise NotFoundError(f"camera {camera_id} not found")
        response = CameraResponse.model_validate(doc)

        deleted = await self._repo.delete(camera_id)
        if not deleted:
            raise NotFoundError(f"camera {camera_id} not found")

        await invalidate(self._redis, self._item_key(camera_id))
        await invalidate(self._redis, self.LIST_KEY)
        await self._publish("deleted", response)
