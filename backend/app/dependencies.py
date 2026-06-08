from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.database import get_database
from app.core.redis import get_redis
from app.repositories.alert_repository import AlertRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.stats_repository import StatsRepository
from app.usecases.alert_usecase import AlertUseCase
from app.usecases.camera_usecase import CameraUseCase
from app.usecases.detection_usecase import DetectionUseCase
from app.usecases.stats_usecase import StatsUseCase


def get_db() -> AsyncIOMotorDatabase:
    return get_database()


def get_camera_repo(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> CameraRepository:
    return CameraRepository(db.cameras)


def get_detection_repo(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> DetectionRepository:
    return DetectionRepository(db.detections)


def get_alert_repo(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AlertRepository:
    return AlertRepository(db.alerts)


def get_stats_repo(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> StatsRepository:
    return StatsRepository(db)


def get_camera_usecase(
    repo: CameraRepository = Depends(get_camera_repo),
    redis: Redis = Depends(get_redis),
) -> CameraUseCase:
    return CameraUseCase(repo, redis)


def get_detection_usecase(
    repo: DetectionRepository = Depends(get_detection_repo),
) -> DetectionUseCase:
    return DetectionUseCase(repo)


def get_alert_usecase(
    repo: AlertRepository = Depends(get_alert_repo),
    redis: Redis = Depends(get_redis),
) -> AlertUseCase:
    return AlertUseCase(repo, redis)


def get_stats_usecase(
    repo: StatsRepository = Depends(get_stats_repo),
) -> StatsUseCase:
    return StatsUseCase(repo)
