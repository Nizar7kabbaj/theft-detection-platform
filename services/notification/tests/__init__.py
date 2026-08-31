from __future__ import annotations

import tempfile
from pathlib import Path

from app.shared.config import settings

_SECRETS = tempfile.TemporaryDirectory()
_SECRETS_DIR = Path(_SECRETS.name)

for _name in ("broker_redis_password", "notify_redis_password"):
    (_SECRETS_DIR / _name).write_text("test-password", encoding="utf-8")

settings.REDIS_PASSWORD_FILE = _SECRETS_DIR / "broker_redis_password"
settings.NOTIFY_REDIS_PASSWORD_FILE = _SECRETS_DIR / "notify_redis_password"
