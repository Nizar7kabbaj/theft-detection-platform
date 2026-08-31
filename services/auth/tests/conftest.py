from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import grpc
import pytest

from app.core import database, keys, pseudonym, redis, security
from app.core.config import get_settings
from app.server import identity


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)


def _reset_value_caches() -> None:
    get_settings.cache_clear()
    keys.load_private_key.cache_clear()
    keys.load_public_key.cache_clear()
    database._load_password.cache_clear()
    redis._load_redis_password.cache_clear()
    pseudonym._load_key.cache_clear()
    security._hasher = None
    identity._cache.clear()


@pytest.fixture(autouse=True)
def reset_caches():
    _reset_value_caches()
    yield
    _reset_value_caches()


class FakeAbortError(Exception):
    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


@dataclass
class FakeServicerContext:
    peer_certificates: tuple[bytes, ...] = ()
    aborted: list[tuple[grpc.StatusCode, str]] = field(default_factory=list)

    async def abort(self, code: grpc.StatusCode, details: str) -> None:
        self.aborted.append((code, details))
        raise FakeAbortError(code, details)

    def auth_context(self) -> dict[str, tuple[bytes, ...]]:
        if not self.peer_certificates:
            return {}
        return {"x509_pem_cert": self.peer_certificates}


@pytest.fixture
def grpc_context() -> FakeServicerContext:
    return FakeServicerContext()
