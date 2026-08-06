from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from typing import Final

HASH_SIZE: Final[int] = 32

HASH_ALGORITHM_UNSPECIFIED: Final[int] = 0
HASH_ALGORITHM_SHA256: Final[int] = 1
DEFAULT_HASH_ALGORITHM: Final[int] = HASH_ALGORITHM_SHA256

_DOMAIN_LEAF: Final[bytes] = b"\x00"
_DOMAIN_CHAIN: Final[bytes] = b"\x01"
_DOMAIN_CHECKPOINT: Final[bytes] = b"\x02"
_DOMAIN_CHECKPOINT_DIGEST: Final[bytes] = b"\x03"

_ALGORITHMS: Final[dict[int, tuple[Callable[[], hashlib._Hash], int]]] = {
    HASH_ALGORITHM_SHA256: (hashlib.sha256, 32),
}

GENESIS_PREV_HASH: Final[bytes] = b"\x00" * HASH_SIZE
GENESIS_CHECKPOINT_HASH: Final[bytes] = b"\x00" * HASH_SIZE


class UnsupportedAlgorithmError(ValueError):
    pass


def digest_size(algorithm: int) -> int:
    entry = _ALGORITHMS.get(algorithm)
    if entry is None:
        raise UnsupportedAlgorithmError(f"unsupported hash algorithm {algorithm}")
    return entry[1]


def is_supported(algorithm: int) -> bool:
    return algorithm in _ALGORITHMS


def genesis_prev_hash(algorithm: int = DEFAULT_HASH_ALGORITHM) -> bytes:
    return b"\x00" * digest_size(algorithm)


def genesis_checkpoint_hash(algorithm: int = DEFAULT_HASH_ALGORITHM) -> bytes:
    return b"\x00" * digest_size(algorithm)


def _new(algorithm: int) -> hashlib._Hash:
    entry = _ALGORITHMS.get(algorithm)
    if entry is None:
        raise UnsupportedAlgorithmError(f"unsupported hash algorithm {algorithm}")
    return entry[0]()


def _u64(value: int) -> bytes:
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"value out of range for uint64: {value}")
    return value.to_bytes(8, "big")


def _length_prefixed(value: bytes) -> bytes:
    return _u64(len(value)) + value


def _constant_time_eq(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


def compute_leaf_hash(
    event_bytes: bytes, algorithm: int = DEFAULT_HASH_ALGORITHM
) -> bytes:
    digest = _new(algorithm)
    digest.update(_DOMAIN_LEAF)
    digest.update(_length_prefixed(event_bytes))
    return digest.digest()


def compute_chain_hash(
    prev_hash: bytes, leaf_hash: bytes, algorithm: int = DEFAULT_HASH_ALGORITHM
) -> bytes:
    size = digest_size(algorithm)
    if len(prev_hash) != size:
        raise ValueError(f"prev_hash must be {size} bytes, got {len(prev_hash)}")
    if len(leaf_hash) != size:
        raise ValueError(f"leaf_hash must be {size} bytes, got {len(leaf_hash)}")
    digest = _new(algorithm)
    digest.update(_DOMAIN_CHAIN)
    digest.update(prev_hash)
    digest.update(leaf_hash)
    return digest.digest()


def leaf_matches(
    event_bytes: bytes, leaf_hash: bytes, algorithm: int = DEFAULT_HASH_ALGORITHM
) -> bool:
    return _constant_time_eq(compute_leaf_hash(event_bytes, algorithm), leaf_hash)


def chain_matches(
    prev_hash: bytes,
    leaf_hash: bytes,
    chain_hash: bytes,
    algorithm: int = DEFAULT_HASH_ALGORITHM,
) -> bool:
    return _constant_time_eq(
        compute_chain_hash(prev_hash, leaf_hash, algorithm), chain_hash
    )


def checkpoint_payload(
    key_id: str,
    tree_size: int,
    tail_sequence_number: int,
    tail_chain_hash: bytes,
    prev_checkpoint_hash: bytes,
    signature_algorithm: int,
    hash_algorithm: int = DEFAULT_HASH_ALGORITHM,
) -> bytes:
    size = digest_size(hash_algorithm)
    if len(tail_chain_hash) != size:
        raise ValueError(
            f"tail_chain_hash must be {size} bytes, got {len(tail_chain_hash)}"
        )
    if len(prev_checkpoint_hash) != size:
        raise ValueError(
            f"prev_checkpoint_hash must be {size} bytes, "
            f"got {len(prev_checkpoint_hash)}"
        )
    parts = [
        _DOMAIN_CHECKPOINT,
        _u64(hash_algorithm),
        _u64(signature_algorithm),
        _length_prefixed(key_id.encode("utf-8")),
        _u64(tree_size),
        _u64(tail_sequence_number),
        _length_prefixed(tail_chain_hash),
        _length_prefixed(prev_checkpoint_hash),
    ]
    return b"".join(parts)


def compute_checkpoint_hash(
    payload: bytes, algorithm: int = DEFAULT_HASH_ALGORITHM
) -> bytes:
    digest = _new(algorithm)
    digest.update(_DOMAIN_CHECKPOINT_DIGEST)
    digest.update(_length_prefixed(payload))
    return digest.digest()


def checkpoint_matches(
    payload: bytes, checkpoint_hash: bytes, algorithm: int = DEFAULT_HASH_ALGORITHM
) -> bool:
    return _constant_time_eq(
        compute_checkpoint_hash(payload, algorithm), checkpoint_hash
    )
