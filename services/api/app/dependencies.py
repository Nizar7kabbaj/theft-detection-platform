import httpx
from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.database import get_database
from app.core.redis import get_redis
from app.repositories.alert_repository import AlertRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.policy_repository import PolicyRepository
from app.repositories.stats_repository import StatsRepository
from app.services.alert_service import AlertClient
from app.services.audit_service import AuditClient
from app.services.inference_service import InferenceClient
from app.usecases.alert_usecase import AlertUseCase
from app.usecases.camera_usecase import CameraUseCase
from app.usecases.detection_usecase import DetectionUseCase
from app.usecases.policy_usecase import PolicyUseCase
from app.usecases.stats_usecase import StatsUseCase


def get_db() -> AsyncIOMotorDatabase:
    return get_database()


def get_stream_redis(request: Request) -> Redis:
    return request.app.state.stream_redis


def get_prometheus(request: Request) -> httpx.AsyncClient:
    return request.app.state.prometheus


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


def get_audit_client(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AuditClient:
    return AuditClient(db)


def get_inference_client(request: Request) -> InferenceClient:
    return InferenceClient(request.app.state.inference_stub)


def get_alert_client(request: Request) -> AlertClient:
    return AlertClient(request.app.state.alert_stub)


def get_policy_repo(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PolicyRepository:
    return PolicyRepository(db.detection_policy)


def get_policy_usecase(
    repo: PolicyRepository = Depends(get_policy_repo),
    stream: Redis = Depends(get_stream_redis),
    audit_client: AuditClient = Depends(get_audit_client),
) -> PolicyUseCase:
    return PolicyUseCase(repo, stream, audit_client)


def get_camera_usecase(
    repo: CameraRepository = Depends(get_camera_repo),
    redis: Redis = Depends(get_redis),
    stream: Redis = Depends(get_stream_redis),
) -> CameraUseCase:
    return CameraUseCase(repo, redis, stream)


def get_alert_usecase(
    repo: AlertRepository = Depends(get_alert_repo),
    redis: Redis = Depends(get_redis),
    alert_client: AlertClient = Depends(get_alert_client),
    audit_client: AuditClient = Depends(get_audit_client),
) -> AlertUseCase:
    return AlertUseCase(repo, redis, alert_client, audit_client)


def get_detection_usecase(
    repo: DetectionRepository = Depends(get_detection_repo),
    alert_usecase: AlertUseCase = Depends(get_alert_usecase),
) -> DetectionUseCase:
    return DetectionUseCase(repo, alert_usecase)


def get_stats_usecase(
    repo: StatsRepository = Depends(get_stats_repo),
    redis: Redis = Depends(get_redis),
) -> StatsUseCase:
    return StatsUseCase(repo, redis)
