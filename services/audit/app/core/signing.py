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
SIGNATURE_ALGORITHM_ML_DSA_44 = 2

_SIGNATURE_SIZES = {
    SIGNATURE_ALGORITHM_ED25519: 64,
    SIGNATURE_ALGORITHM_ML_DSA_44: 2420,
}


class SigningKeyError(RuntimeError):
    pass


class UnknownKeyError(SigningKeyError):
    pass


def signature_size(algorithm: int) -> int:
    size = _SIGNATURE_SIZES.get(algorithm)
    if size is None:
        raise SigningKeyError(f"unsupported signature algorithm {algorithm}")
    return size


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
    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool: ...


def _read_key_file(path: Path, label: str) -> bytes:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise SigningKeyError(f"{label} missing at {path}") from exc
    except OSError as exc:
        raise SigningKeyError(f"{label} unreadable at {path}") from exc
    if not data.strip():
        raise SigningKeyError(f"{label} empty at {path}")
    return data


class PublicKeyring:
    def __init__(self, directory: Path, active_key_id: str, active_public_key: Path) -> None:
        self._directory = directory
        self._active_key_id = active_key_id
        self._active_public_key = active_public_key
        self._keys: dict[str, Ed25519PublicKey] = {}

    def _load(self, key_id: str) -> Ed25519PublicKey:
        if key_id == self._active_key_id:
            path = self._active_public_key
        else:
            path = self._directory / f"checkpoint_public_{key_id}.pem"
        data = _read_key_file(path, f"checkpoint public key {key_id}")
        try:
            loaded = load_pem_public_key(data)
        except (ValueError, TypeError) as exc:
            raise SigningKeyError(
                f"checkpoint public key {key_id} is not valid pem"
            ) from exc
        if not isinstance(loaded, Ed25519PublicKey):
            raise SigningKeyError(f"checkpoint public key {key_id} is not ed25519")
        return loaded

    def get(self, key_id: str) -> Ed25519PublicKey:
        if not key_id:
            raise UnknownKeyError("checkpoint key id is empty")
        if key_id not in self._keys:
            try:
                self._keys[key_id] = self._load(key_id)
            except SigningKeyError as exc:
                raise UnknownKeyError(str(exc)) from exc
        return self._keys[key_id]


class LocalFileSigner(CheckpointSigner):
    def __init__(
        self,
        private_key_file: Path,
        public_key_file: Path,
        key_identifier: str,
        keyring: PublicKeyring,
    ) -> None:
        self._private_key_file = private_key_file
        self._public_key_file = public_key_file
        self._key_id = key_identifier
        self._keyring = keyring
        self._private: Ed25519PrivateKey | None = None

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def signature_algorithm(self) -> int:
        return SIGNATURE_ALGORITHM_ED25519

    def _private_key(self) -> Ed25519PrivateKey:
        if self._private is None:
            data = _read_key_file(self._private_key_file, "checkpoint private key")
            try:
                loaded = load_pem_private_key(data, password=None)
            except (ValueError, TypeError) as exc:
                raise SigningKeyError("checkpoint private key is not valid pem") from exc
            if not isinstance(loaded, Ed25519PrivateKey):
                raise SigningKeyError("checkpoint private key is not ed25519")
            public = loaded.public_key()
            expected = self._keyring.get(self._key_id)
            if public.public_bytes_raw() != expected.public_bytes_raw():
                raise SigningKeyError(
                    "checkpoint private key does not match the published public key"
                )
            self._private = loaded
        return self._private

    def sign(self, payload: bytes) -> bytes:
        return self._private_key().sign(payload)

    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        try:
            public = self._keyring.get(key_id)
        except UnknownKeyError:
            logger.warning("checkpoint signed under unknown key id")
            return False
        try:
            public.verify(signature, payload)
        except InvalidSignature:
            return False
        return True


class VerifyOnlySigner(CheckpointSigner):
    def __init__(self, key_identifier: str, keyring: PublicKeyring) -> None:
        self._key_id = key_identifier
        self._keyring = keyring

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def signature_algorithm(self) -> int:
        return SIGNATURE_ALGORITHM_ED25519

    def sign(self, payload: bytes) -> bytes:
        raise SigningKeyError("signing is not available without a private key")

    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        try:
            public = self._keyring.get(key_id)
        except UnknownKeyError:
            logger.warning("checkpoint signed under unknown key id")
            return False
        try:
            public.verify(signature, payload)
        except InvalidSignature:
            return False
        return True


@lru_cache(maxsize=1)
def get_keyring() -> PublicKeyring:
    settings = get_settings()
    return PublicKeyring(
        settings.checkpoint_public_key_file.parent,
        settings.checkpoint_key_id,
        settings.checkpoint_public_key_file,
    )


@lru_cache(maxsize=1)
def get_signer() -> CheckpointSigner:
    settings = get_settings()
    keyring = get_keyring()
    if not settings.checkpoint_private_key_file.exists():
        logger.info("checkpoint private key absent, running verify only")
        return VerifyOnlySigner(settings.checkpoint_key_id, keyring)
    return LocalFileSigner(
        settings.checkpoint_private_key_file,
        settings.checkpoint_public_key_file,
        settings.checkpoint_key_id,
        keyring,
    )


def build_checkpoint_payload(
    key_id: str,
    tree_size: int,
    tail_sequence_number: int,
    tail_chain_hash: bytes,
    prev_checkpoint_hash: bytes,
    signature_algorithm: int = SIGNATURE_ALGORITHM_ED25519,
    hash_algorithm: int = DEFAULT_HASH_ALGORITHM,
) -> bytes:
    return checkpoint_payload(
        key_id=key_id,
        tree_size=tree_size,
        tail_sequence_number=tail_sequence_number,
        tail_chain_hash=tail_chain_hash,
        prev_checkpoint_hash=prev_checkpoint_hash,
        signature_algorithm=signature_algorithm,
        hash_algorithm=hash_algorithm,
    )


def reset_signer_cache() -> None:
    get_signer.cache_clear()
    get_keyring.cache_clear()
