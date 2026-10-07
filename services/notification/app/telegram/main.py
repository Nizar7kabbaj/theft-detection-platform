from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable
from typing import Any

import grpc
from kombu.exceptions import OperationalError
from opentelemetry.instrumentation.grpc import aio_client_interceptors
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from redis.asyncio import Redis

from app.core.database import close_mongodb_connection, connect_to_mongodb, get_collection
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.server.grpc_gen.auth_pb2_grpc import AuthServiceStub
from app.server.grpc_gen.decision_pb2_grpc import AlertDecisionServiceStub
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.observability import setup_base
from app.shared.telegram_service import (
    TelegramError,
    TelegramPermanentError,
    delete_webhook,
    get_updates,
    open_client,
)
from app.telegram.handlers import Context, handle_update
from app.telegram.lease import Lease
from app.worker.observability import instrument_telegram_http

logger = logging.getLogger(__name__)

_STANDBY_SEC = 5.0
_BACKOFF_SEC = 5.0


def _touch() -> None:
    settings.HEARTBEAT_FILE.touch()


def _open_redis() -> Redis:
    options: dict[str, Any] = {}
    if settings.REDIS_TLS:
        options = {
            "ssl_ca_certs": str(settings.TLS_CA_FILE),
            "ssl_certfile": str(settings.TLS_CERT_FILE),
            "ssl_keyfile": str(settings.TLS_KEY_FILE),
            "ssl_cert_reqs": "required",
        }
    return Redis.from_url(
        settings.NOTIFY_REDIS_URL,
        socket_connect_timeout=2.0,
        socket_timeout=5.0,
        decode_responses=True,
        **options,
    )


def _open_channel(target: str, credentials: grpc.ChannelCredentials) -> grpc.aio.Channel:
    return grpc.aio.secure_channel(target, credentials, interceptors=aio_client_interceptors())


async def _enqueue_display(alert_id: str, decision: str, decided_by: str, decided_at: str) -> None:
    try:
        await asyncio.to_thread(
            celery_app.send_task,
            "app.worker.tasks.apply_decision_task",
            args=[alert_id, decision, decided_by, decided_at],
        )
    except OperationalError as exc:
        logger.warning("decision resync enqueue failed for alert %s: %s", alert_id, exc)


async def _or_stop(work: Awaitable[Any], stop: asyncio.Event) -> Any | None:
    fetch = asyncio.ensure_future(work)
    waiter = asyncio.ensure_future(stop.wait())
    done, pending = await asyncio.wait({fetch, waiter}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if fetch in done:
        return fetch.result()
    return None


async def _poll(ctx: Context, lease: Lease, stop: asyncio.Event) -> None:
    offset = 0
    while not stop.is_set():
        if not await lease.renew():
            logger.warning("poller lease lost, stopping polls")
            return
        try:
            updates = await _or_stop(
                get_updates(ctx.telegram, offset, settings.TELEGRAM_POLL_TIMEOUT_SEC), stop
            )
        except TelegramPermanentError as exc:
            logger.error("telegram polling refused: %s", exc)
            return
        except TelegramError as exc:
            logger.warning("telegram polling failed: %s", exc)
            await _or_stop(asyncio.sleep(_BACKOFF_SEC), stop)
            continue
        _touch()
        if updates is None:
            return
        for update in updates:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            try:
                await handle_update(ctx, update)
            except Exception:
                logger.exception("telegram update handling failed")


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    await connect_to_mongodb()
    redis = _open_redis()
    credentials = grpc.ssl_channel_credentials(
        root_certificates=settings.TLS_CA_FILE.read_bytes(),
        private_key=settings.TLS_KEY_FILE.read_bytes(),
        certificate_chain=settings.TLS_CERT_FILE.read_bytes(),
    )
    decision_channel = _open_channel(settings.DECISION_TARGET, credentials)
    auth_channel = _open_channel(settings.AUTH_TARGET, credentials)
    lease = Lease(redis, settings.POLLER_LEASE_KEY, settings.POLLER_LEASE_TTL_SEC * 1000)
    try:
        async with open_client() as telegram:
            ctx = Context(
                telegram=telegram,
                decisions=AlertDecisionServiceStub(decision_channel),
                auth=AuthServiceStub(auth_channel),
                redis=redis,
                resync=_enqueue_display,
                intents=DeliveryIntentRepository(
                    get_collection(settings.DELIVERY_INTENT_COLLECTION)
                ),
            )
            await delete_webhook(telegram)
            logger.info("telegram poller started")
            while not stop.is_set():
                _touch()
                if not await lease.acquire():
                    await _or_stop(asyncio.sleep(_STANDBY_SEC), stop)
                    continue
                logger.info("poller lease acquired")
                try:
                    await _poll(ctx, lease, stop)
                finally:
                    await lease.release()
    finally:
        await asyncio.gather(
            decision_channel.close(grace=2),
            auth_channel.close(grace=2),
            return_exceptions=True,
        )
        with contextlib.suppress(Exception):
            await redis.aclose()
        await close_mongodb_connection()
        logger.info("telegram poller stopped")


def main() -> None:
    setup_base(service_name="notification-telegram")
    LoggingInstrumentor().instrument(set_logging_format=False)
    instrument_telegram_http()
    asyncio.run(run())


if __name__ == "__main__":
    main()
