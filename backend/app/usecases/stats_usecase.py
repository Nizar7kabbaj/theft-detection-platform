from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from app.core.cache import get_or_set
from app.repositories.stats_repository import StatsRepository
from app.schemas.stats import StatsResponse


class StatsUseCase:
    OVERVIEW_KEY = "cache:stats:overview"
    TTL = 10

    def __init__(self, repo: StatsRepository, redis: Redis) -> None:
        self._repo = repo
        self._redis = redis

    async def overview(self) -> StatsResponse:
        async def loader() -> dict:
            (
                total_alerts,
                total_detections,
                total_cameras,
                alerts_today,
                high_severity,
                medium_severity,
                top_objects,
            ) = await asyncio.gather(
                self._repo.count_alerts(),
                self._repo.count_detections(),
                self._repo.count_cameras(),
                self._repo.count_alerts_today(),
                self._repo.count_by_severity("HIGH"),
                self._repo.count_by_severity("MEDIUM"),
                self._repo.top_objects(),
            )
            return StatsResponse(
                total_alerts=total_alerts,
                total_detections=total_detections,
                total_cameras=total_cameras,
                alerts_today=alerts_today,
                high_severity=high_severity,
                medium_severity=medium_severity,
                top_objects=top_objects,
            ).model_dump(mode="json")

        cached = await get_or_set(self._redis, self.OVERVIEW_KEY, self.TTL, loader)
        return StatsResponse.model_validate(cached)
