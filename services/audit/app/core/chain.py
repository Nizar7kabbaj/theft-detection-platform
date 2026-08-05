from __future__ import annotations

import hashlib

HASH_SIZE = 32
GENESIS_PREV_HASH = b"\x00" * HASH_SIZE


def compute_chain_hash(prev_hash: bytes, event_bytes: bytes) -> bytes:
    if len(prev_hash) != HASH_SIZE:
        raise ValueError(f"prev_hash must be {HASH_SIZE} bytes, got {len(prev_hash)}")
    digest = hashlib.sha256()
    digest.update(prev_hash)
    digest.update(event_bytes)
    return digest.digest()
