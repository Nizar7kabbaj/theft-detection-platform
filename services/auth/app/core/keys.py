from __future__ import annotations


import logging
from functools import lru_cache
from app.core.config import get_settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_private_key() -> str:
    path = get_settings().jwt_private_key_file
    try:
        key = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("jwt private key file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("jwt private key file unreadable at %s: %s", path, exc)
        return ""
    if not key:
        logger.error("jwt private key file empty at %s", path)
    return key


@lru_cache(maxsize=1)
def load_public_key() -> str:
    path = get_settings().jwt_public_key_file
    try:
        key = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("jwt public key file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("jwt public key file unreadable at %s: %s", path, exc)
        return ""
    if not key:
        logger.error("jwt public key file empty at %s", path)
    return key
