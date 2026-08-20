from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.core.cache import get_or_set, make_list_key
from app.core.errors import ValidationError
from app.repositories.stats_repository import StatsRepository
from app.schemas.stats import (
    AlertBucket,
    BucketUnit,
    DecisionBucket,
    StatsResponse,
    StatsTimeseriesResponse,
)

_HIGH = ["SEVERITY_WARNING", "SEVERITY_CRITICAL"]
_MEDIUM = ["SEVERITY_NOTICE"]

_SEVERITY_FIELDS = {
    "SEVERITY_CRITICAL": "critical",
    "SEVERITY_WARNING": "warning",
    "SEVERITY_NOTICE": "notice",
    "SEVERITY_INFO": "info",
    "SEVERITY_UNSPECIFIED": "unspecified",
}

_DECISION_FIELDS = {
    "DECISION_CONFIRMED": "confirmed",
    "DECISION_DISMISSED": "dismissed",
    "DECISION_UNSURE": "unsure",
}

_STEP = {BucketUnit.HOUR: timedelta(hours=1), BucketUnit.DAY: timedelta(days=1)}


def _truncate(moment: datetime, unit: BucketUnit) -> datetime:
    floored = moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if unit is BucketUnit.DAY:
        return floored.replace(hour=0)
    return floored


class StatsUseCase:
    OVERVIEW_KEY = "cache:stats:overview"
    TTL = 10
    TIMESERIES_TTL = 30
    MAX_BUCKETS = 500

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
                self._repo.count_by_severity(_HIGH),
                self._repo.count_by_severity(_MEDIUM),
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

    def _resolve_window(
        self,
        start: datetime | None,
        end: datetime | None,
        unit: BucketUnit,
    ) -> tuple[datetime, datetime]:
        step = _STEP[unit]
        stop = _truncate(end or datetime.now(UTC), unit) + step
        default_span = step * (24 if unit is BucketUnit.HOUR else 30)
        begin = _truncate(start, unit) if start else stop - default_span
        if begin >= stop:
            raise ValidationError("start must fall before end")
        span = (stop - begin) // step
        if span > self.MAX_BUCKETS:
            begin = stop - step * self.MAX_BUCKETS
        return begin, stop

    async def timeseries(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        unit: BucketUnit = BucketUnit.HOUR,
    ) -> StatsTimeseriesResponse:
        begin, stop = self._resolve_window(start, end, unit)
        key = make_list_key(
            "stats:timeseries",
            {"start": begin.isoformat(), "end": stop.isoformat(), "unit": unit.value},
        )

        async def loader() -> dict:
            alert_rows, decision_rows = await asyncio.gather(
                self._repo.alerts_over_time(begin, stop, unit.value),
                self._repo.decisions_over_time(begin, stop, unit.value),
            )
            return StatsTimeseriesResponse(
                start=begin,
                end=stop,
                unit=unit,
                alerts=self._fill_alerts(alert_rows, begin, stop, unit),
                decisions=self._fill_decisions(decision_rows, begin, stop, unit),
            ).model_dump(mode="json")

        cached = await get_or_set(self._redis, key, self.TIMESERIES_TTL, loader)
        return StatsTimeseriesResponse.model_validate(cached)

    def _fill_alerts(
        self,
        rows: list[dict],
        begin: datetime,
        stop: datetime,
        unit: BucketUnit,
    ) -> list[AlertBucket]:
        counts: dict[datetime, dict[str, int]] = {}
        for row in rows:
            field = _SEVERITY_FIELDS.get(row["severity"])
            if field is None:
                continue
            slot = counts.setdefault(row["bucket"].astimezone(UTC), {})
            slot[field] = slot.get(field, 0) + row["count"]
        buckets: list[AlertBucket] = []
        for moment in self._walk(begin, stop, unit):
            slot = counts.get(moment, {})
            values = {field: slot.get(field, 0) for field in _SEVERITY_FIELDS.values()}
            buckets.append(AlertBucket(bucket=moment, total=sum(values.values()), **values))
        return buckets

    def _fill_decisions(
        self,
        rows: list[dict],
        begin: datetime,
        stop: datetime,
        unit: BucketUnit,
    ) -> list[DecisionBucket]:
        counts: dict[datetime, dict[str, int]] = {}
        for row in rows:
            field = _DECISION_FIELDS.get(row["decision"])
            if field is None:
                continue
            slot = counts.setdefault(row["bucket"].astimezone(UTC), {})
            slot[field] = slot.get(field, 0) + row["count"]
        buckets: list[DecisionBucket] = []
        for moment in self._walk(begin, stop, unit):
            slot = counts.get(moment, {})
            values = {field: slot.get(field, 0) for field in _DECISION_FIELDS.values()}
            buckets.append(DecisionBucket(bucket=moment, total=sum(values.values()), **values))
        return buckets

    @staticmethod
    def _walk(begin: datetime, stop: datetime, unit: BucketUnit) -> list[datetime]:
        step = _STEP[unit]
        moments: list[datetime] = []
        cursor = begin
        while cursor < stop:
            moments.append(cursor)
            cursor += step
        return moments
