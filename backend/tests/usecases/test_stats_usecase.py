from __future__ import annotations

import json

import pytest

from app.schemas.stats import StatsResponse


def _sample_response_dict() -> dict:
    return StatsResponse(
        total_alerts=10,
        total_detections=42,
        total_cameras=3,
        alerts_today=2,
        high_severity=4,
        medium_severity=6,
        top_objects=[
            {"object": "phone", "count": 5},
            {"object": None, "count": 2},
        ],
    ).model_dump(mode="json")


class TestOverview:
    async def test_returns_parsed_response_from_cache(self, stats_usecase, mock_redis):
        mock_redis.get.return_value = json.dumps(_sample_response_dict())

        result = await stats_usecase.overview()

        assert isinstance(result, StatsResponse)
        assert result.total_alerts == 10
        assert result.top_objects[0].object == "phone"
        assert result.top_objects[1].object is None

    async def test_cache_miss_pulls_from_repo(
        self, stats_usecase, mock_redis, fake_stats_repo
    ):
        mock_redis.get.return_value = None
        fake_stats_repo.counts.update(
            {"alerts": 7, "detections": 30, "cameras": 2, "alerts_today": 1, "HIGH": 3, "MEDIUM": 4}
        )
        fake_stats_repo.top = [{"object": "knife", "count": 3}]

        result = await stats_usecase.overview()

        assert result.total_alerts == 7
        assert result.total_detections == 30
        assert result.total_cameras == 2
        assert result.alerts_today == 1
        assert result.high_severity == 3
        assert result.medium_severity == 4
        assert result.top_objects[0].object == "knife"
        assert result.top_objects[0].count == 3

    async def test_cache_miss_returns_response_model(self, stats_usecase, mock_redis):
        mock_redis.get.return_value = None

        result = await stats_usecase.overview()

        assert isinstance(result, StatsResponse)
        assert result.total_alerts == 0
        assert result.top_objects == []

    async def test_top_objects_with_none_class_name_round_trip(
        self, stats_usecase, mock_redis, fake_stats_repo
    ):
        mock_redis.get.return_value = None
        fake_stats_repo.top = [
            {"object": None, "count": 4},
            {"object": "bag", "count": 1},
        ]

        result = await stats_usecase.overview()

        assert result.top_objects[0].object is None
        assert result.top_objects[0].count == 4
        assert result.top_objects[1].object == "bag"

    async def test_cache_key_matches_constant(self, stats_usecase, mock_redis):
        mock_redis.get.return_value = None

        await stats_usecase.overview()

        mock_redis.get.assert_awaited_with("cache:stats:overview")
