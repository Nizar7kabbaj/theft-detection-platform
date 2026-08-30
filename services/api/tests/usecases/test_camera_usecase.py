from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.schemas.camera import CameraCreate, CameraResponse
from app.services.camera_health import HealthState


def _camera_create() -> CameraCreate:
    return CameraCreate(
        camera_id="cam-a",
        name="front-door",
        location="entrance",
        stream_url="rtsp://cam-1/stream",
        status="active",
    )


@pytest.fixture(autouse=True)
def patch_health(mocker):
    mocker.patch(
        "app.usecases.camera_usecase.read_health",
        new=mocker.AsyncMock(
            return_value=mocker.MagicMock(
                state=HealthState.UNKNOWN,
                last_frame_at=None,
                age_seconds=None,
            )
        ),
    )


class TestCreate:
    async def test_persists_camera_and_returns_response(self, camera_usecase, fake_camera_repo):
        response = await camera_usecase.create(_camera_create())

        assert isinstance(response, CameraResponse)
        assert response.name == "front-door"
        assert response.location == "entrance"
        assert len(fake_camera_repo.store) == 1
        stored = next(iter(fake_camera_repo.store.values()))
        assert isinstance(stored["created_at"], datetime)

    async def test_raises_conflict_on_duplicate_name(self, camera_usecase):
        await camera_usecase.create(_camera_create())

        with pytest.raises(ConflictError, match="already exists"):
            await camera_usecase.create(_camera_create())

    async def test_invalidates_list_cache(self, camera_usecase, mock_redis):
        await camera_usecase.create(_camera_create())

        mock_redis.delete.assert_any_call("cache:cameras:list")

    async def test_publishes_created_event(self, camera_usecase, mock_redis):
        response = await camera_usecase.create(_camera_create())

        mock_redis.publish.assert_awaited_once()
        channel, payload = mock_redis.publish.await_args.args
        assert channel == "cameras:created"
        published = json.loads(payload)
        assert published["name"] == response.name
        assert published["_id"] == response.id


class TestList:
    async def test_returns_cached_responses_when_present(
        self, camera_usecase, mock_redis, sample_camera_doc
    ):
        cached_item = CameraResponse.model_validate(sample_camera_doc).model_dump(
            mode="json", by_alias=True
        )
        mock_redis.get.return_value = json.dumps([cached_item])

        result = await camera_usecase.list()

        assert len(result) == 1
        assert result[0].id == sample_camera_doc["_id"]

    async def test_empty_store_returns_empty_list(self, camera_usecase, mock_redis):
        mock_redis.get.return_value = None

        result = await camera_usecase.list()

        assert result == []

    async def test_loader_pulls_from_repo_on_cache_miss(
        self, camera_usecase, mock_redis, fake_camera_repo, sample_camera_doc
    ):
        mock_redis.get.return_value = None
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}

        result = await camera_usecase.list()

        assert len(result) == 1
        assert result[0].name == "front-door"


class TestGet:
    async def test_returns_camera_from_repo(
        self, camera_usecase, mock_redis, fake_camera_repo, sample_camera_doc
    ):
        mock_redis.get.return_value = None
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}

        result = await camera_usecase.get(sample_camera_doc["_id"])

        assert result.id == sample_camera_doc["_id"]
        assert result.name == "front-door"

    async def test_missing_camera_raises_not_found(self, camera_usecase, mock_redis):
        mock_redis.get.return_value = None

        with pytest.raises(NotFoundError, match="not found"):
            await camera_usecase.get("missing-id")


class TestDelete:
    async def test_removes_camera(self, camera_usecase, fake_camera_repo, sample_camera_doc):
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}

        await camera_usecase.delete(sample_camera_doc["_id"])

        assert sample_camera_doc["_id"] not in fake_camera_repo.store

    async def test_raises_not_found_for_missing_camera(self, camera_usecase):
        with pytest.raises(NotFoundError, match="not found"):
            await camera_usecase.delete("missing-id")

    async def test_publishes_deleted_event_with_full_response(
        self, camera_usecase, fake_camera_repo, mock_redis, sample_camera_doc
    ):
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}

        await camera_usecase.delete(sample_camera_doc["_id"])

        publish_calls = [
            c for c in mock_redis.publish.await_args_list if c.args[0] == "cameras:deleted"
        ]
        assert len(publish_calls) == 1
        published = json.loads(publish_calls[0].args[1])
        assert published["_id"] == sample_camera_doc["_id"]
        assert published["name"] == "front-door"

    async def test_publish_failure_does_not_raise(
        self, camera_usecase, fake_camera_repo, mock_redis, sample_camera_doc
    ):
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}
        mock_redis.publish.side_effect = Exception("redis down")

        await camera_usecase.delete(sample_camera_doc["_id"])

        assert sample_camera_doc["_id"] not in fake_camera_repo.store

    async def test_invalidates_item_and_list_cache(
        self, camera_usecase, fake_camera_repo, mock_redis, sample_camera_doc
    ):
        fake_camera_repo.store[sample_camera_doc["_id"]] = {**sample_camera_doc}

        await camera_usecase.delete(sample_camera_doc["_id"])

        delete_calls = [c.args[0] for c in mock_redis.delete.await_args_list]
        assert f"cache:cameras:{sample_camera_doc['_id']}" in delete_calls
        assert "cache:cameras:list" in delete_calls
