from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)

from app.core.chain import DEFAULT_HASH_ALGORITHM, checkpoint_payload
from app.core.config import get_settings

logger = logging.getLogger(__name__)

SIGNATURE_ALGORITHM_UNSPECIFIED = 0
SIGNATURE_ALGORITHM_ED25519 = 1


class SigningKeyError(RuntimeError):
    pass


class CheckpointSigner(ABC):
    @property
    @abstractmethod
    def key_id(self) -> str: ...

    @property
    @abstractmethod
    def signature_algorithm(self) -> int: ...

    @abstractmethod
    def sign(self, payload: bytes) -> bytes: ...

    @abstractmethod
    def verify(self, payload: bytes, signature: bytes) -> bool: ...


class LocalFileSigner(CheckpointSigner):
    def __init__(
        self, private_key_file: Path, public_key_file: Path, key_identifier: str
    ) -> None:
        self._private_key_file = private_key_file
        self._public_key_file = public_key_file
        self._key_id = key_identifier
        self._private: Ed25519PrivateKey | None = None
        self._public: Ed25519PublicKey | None = None

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def signature_algorithm(self) -> int:
        return SIGNATURE_ALGORITHM_ED25519

    def _read(self, path: Path, label: str) -> bytes:
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise SigningKeyError(f"{label} missing at {path}") from exc
        except OSError as exc:
            raise SigningKeyError(f"{label} unreadable at {path}") from exc
        if not data.strip():
            raise SigningKeyError(f"{label} empty at {path}")
        return data

    def _private_key(self) -> Ed25519PrivateKey:
        if self._private is None:
            data = self._read(self._private_key_file, "checkpoint private key")
            try:
                loaded = load_pem_private_key(data, password=None)
            except (ValueError, TypeError) as exc:
                raise SigningKeyError("checkpoint private key is not valid pem") from exc
            if not isinstance(loaded, Ed25519PrivateKey):
                raise SigningKeyError("checkpoint private key is not ed25519")
            self._private = loaded
        return self._private

    def _public_key(self) -> Ed25519PublicKey:
        if self._public is None:
            data = self._read(self._public_key_file, "checkpoint public key")
            try:
                loaded = load_pem_public_key(data)
            except (ValueError, TypeError) as exc:
                raise SigningKeyError("checkpoint public key is not valid pem") from exc
            if not isinstance(loaded, Ed25519PublicKey):
                raise SigningKeyError("checkpoint public key is not ed25519")
            self._public = loaded
        return self._public

    def sign(self, payload: bytes) -> bytes:
        return self._private_key().sign(payload)

    def verify(self, payload: bytes, signature: bytes) -> bool:
        try:
            self._public_key().verify(signature, payload)
        except InvalidSignature:
            return False
        return True


class VerifyOnlySigner(CheckpointSigner):
    def __init__(self, public_key_file: Path, key_identifier: str) -> None:
        self._delegate = LocalFileSigner(public_key_file, public_key_file, key_identifier)

    @property
    def key_id(self) -> str:
        return self._delegate.key_id

    @property
    def signature_algorithm(self) -> int:
        return SIGNATURE_ALGORITHM_ED25519

    def sign(self, payload: bytes) -> bytes:
        raise SigningKeyError("signing is not available in verify-only mode")

    def verify(self, payload: bytes, signature: bytes) -> bool:
        return self._delegate.verify(payload, signature)


@lru_cache(maxsize=1)
def get_signer() -> CheckpointSigner:
    settings = get_settings()
    return LocalFileSigner(
        settings.checkpoint_private_key_file,
        settings.checkpoint_public_key_file,
        settings.checkpoint_key_id,
    )


def build_checkpoint_payload(
    key_id: str,
    tree_size: int,
    tail_sequence_number: int,
    tail_chain_hash: bytes,
    hash_algorithm: int = DEFAULT_HASH_ALGORITHM,
) -> bytes:
    return checkpoint_payload(
        key_id=key_id,
        tree_size=tree_size,
        tail_sequence_number=tail_sequence_number,
        tail_chain_hash=tail_chain_hash,
        hash_algorithm=hash_algorithm,
    )


def reset_signer_cache() -> None:
    get_signer.cache_clear()
