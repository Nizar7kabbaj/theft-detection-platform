import asyncio

from app.repositories.stats_repository import StatsRepository
from app.schemas.stats import StatsResponse


class StatsUseCase:
    def __init__(self, repo: StatsRepository) -> None:
        self._repo = repo

    async def overview(self) -> StatsResponse:
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
        )
