from __future__ import annotations

from pathlib import Path

import pytest

from app.core import signing
from app.core.chain import compute_checkpoint_hash
from app.core.config import get_settings
from tests import (
    CHECKPOINT_KEY_ID,
    CHECKPOINT_PRIVATE_KEY_FILE,
    CHECKPOINT_PUBLIC_KEY_FILE,
    ed25519_pem_pair,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def keyring() -> signing.PublicKeyring:
    return signing.PublicKeyring(
        CHECKPOINT_PUBLIC_KEY_FILE.parent,
        CHECKPOINT_KEY_ID,
        CHECKPOINT_PUBLIC_KEY_FILE,
    )


@pytest.fixture
def signer(keyring: signing.PublicKeyring) -> signing.LocalFileSigner:
    return signing.LocalFileSigner(
        CHECKPOINT_PRIVATE_KEY_FILE,
        CHECKPOINT_PUBLIC_KEY_FILE,
        CHECKPOINT_KEY_ID,
        keyring,
    )


def test_signature_size_of_ed25519() -> None:
    assert signing.signature_size(signing.SIGNATURE_ALGORITHM_ED25519) == 64


def test_signature_size_of_ml_dsa_44() -> None:
    assert signing.signature_size(signing.SIGNATURE_ALGORITHM_ML_DSA_44) == 2420


@pytest.mark.parametrize("algorithm", [0, 3, -1])
def test_signature_size_rejects_unknown_algorithm(algorithm: int) -> None:
    with pytest.raises(signing.SigningKeyError, match="unsupported signature algorithm"):
        signing.signature_size(algorithm)


def test_keyring_loads_the_active_public_key(keyring: signing.PublicKeyring) -> None:
    assert keyring.get(CHECKPOINT_KEY_ID) is not None


def test_keyring_caches_the_loaded_key(keyring: signing.PublicKeyring) -> None:
    first = keyring.get(CHECKPOINT_KEY_ID)
    assert keyring.get(CHECKPOINT_KEY_ID) is first


def test_keyring_rejects_empty_key_id(keyring: signing.PublicKeyring) -> None:
    with pytest.raises(signing.UnknownKeyError, match="key id is empty"):
        keyring.get("")


def test_keyring_rejects_absent_key_id(keyring: signing.PublicKeyring) -> None:
    with pytest.raises(signing.UnknownKeyError, match="missing"):
        keyring.get("c9")


def test_keyring_loads_a_retired_key_from_the_directory(
    keyring: signing.PublicKeyring, tmp_path: Path
) -> None:
    _, public_pem = ed25519_pem_pair()
    retired = CHECKPOINT_PUBLIC_KEY_FILE.parent / "checkpoint_public_c0.pem"
    retired.write_bytes(public_pem)
    try:
        assert keyring.get("c0") is not None
    finally:
        retired.unlink()


def test_keyring_rejects_a_key_file_that_is_not_pem(
    keyring: signing.PublicKeyring,
) -> None:
    broken = CHECKPOINT_PUBLIC_KEY_FILE.parent / "checkpoint_public_c8.pem"
    broken.write_bytes(b"not a pem file at all")
    try:
        with pytest.raises(signing.UnknownKeyError, match="not valid pem"):
            keyring.get("c8")
    finally:
        broken.unlink()


def test_keyring_rejects_an_empty_key_file(keyring: signing.PublicKeyring) -> None:
    empty = CHECKPOINT_PUBLIC_KEY_FILE.parent / "checkpoint_public_c7.pem"
    empty.write_bytes(b"   \n")
    try:
        with pytest.raises(signing.UnknownKeyError, match="empty"):
            keyring.get("c7")
    finally:
        empty.unlink()


def test_signer_reports_ed25519(signer: signing.LocalFileSigner) -> None:
    assert signer.signature_algorithm == signing.SIGNATURE_ALGORITHM_ED25519
    assert signer.key_id == CHECKPOINT_KEY_ID


def test_sign_produces_a_sixty_four_byte_signature(signer: signing.LocalFileSigner) -> None:
    assert len(signer.sign(b"payload")) == 64


def test_sign_and_verify_round_trip(signer: signing.LocalFileSigner) -> None:
    payload = b"checkpoint-payload"
    assert signer.verify(payload, signer.sign(payload), CHECKPOINT_KEY_ID) is True


def test_verify_rejects_an_altered_payload(signer: signing.LocalFileSigner) -> None:
    signature = signer.sign(b"checkpoint-payload")
    assert signer.verify(b"checkpoint-payload-forged", signature, CHECKPOINT_KEY_ID) is False


def test_verify_rejects_a_corrupted_signature(signer: signing.LocalFileSigner) -> None:
    payload = b"checkpoint-payload"
    signature = bytearray(signer.sign(payload))
    signature[0] ^= 0xFF
    assert signer.verify(payload, bytes(signature), CHECKPOINT_KEY_ID) is False


def test_verify_rejects_a_truncated_signature(signer: signing.LocalFileSigner) -> None:
    payload = b"checkpoint-payload"
    assert signer.verify(payload, signer.sign(payload)[:32], CHECKPOINT_KEY_ID) is False


def test_verify_rejects_an_unknown_key_id(signer: signing.LocalFileSigner) -> None:
    payload = b"checkpoint-payload"
    assert signer.verify(payload, signer.sign(payload), "c9") is False


def test_verify_rejects_a_signature_from_a_foreign_key(
    signer: signing.LocalFileSigner, keyring: signing.PublicKeyring
) -> None:
    foreign_private, foreign_public = ed25519_pem_pair()
    retired = CHECKPOINT_PUBLIC_KEY_FILE.parent / "checkpoint_public_c6.pem"
    retired.write_bytes(foreign_public)
    foreign_private_file = CHECKPOINT_PUBLIC_KEY_FILE.parent / "foreign_private.pem"
    foreign_private_file.write_bytes(foreign_private)
    try:
        foreign_signer = signing.LocalFileSigner(foreign_private_file, retired, "c6", keyring)
        signature = foreign_signer.sign(b"checkpoint-payload")
        assert signer.verify(b"checkpoint-payload", signature, CHECKPOINT_KEY_ID) is False
    finally:
        retired.unlink()
        foreign_private_file.unlink()


def test_private_key_that_does_not_match_the_published_public_key_is_refused(
    keyring: signing.PublicKeyring,
) -> None:
    foreign_private, _ = ed25519_pem_pair()
    mismatched = CHECKPOINT_PUBLIC_KEY_FILE.parent / "mismatched_private.pem"
    mismatched.write_bytes(foreign_private)
    try:
        rogue = signing.LocalFileSigner(
            mismatched, CHECKPOINT_PUBLIC_KEY_FILE, CHECKPOINT_KEY_ID, keyring
        )
        with pytest.raises(signing.SigningKeyError, match="does not match the published"):
            rogue.sign(b"payload")
    finally:
        mismatched.unlink()


def test_missing_private_key_file_is_refused(keyring: signing.PublicKeyring) -> None:
    absent = CHECKPOINT_PUBLIC_KEY_FILE.parent / "absent_private.pem"
    rogue = signing.LocalFileSigner(absent, CHECKPOINT_PUBLIC_KEY_FILE, CHECKPOINT_KEY_ID, keyring)
    with pytest.raises(signing.SigningKeyError, match="missing"):
        rogue.sign(b"payload")


def test_private_key_that_is_not_pem_is_refused(keyring: signing.PublicKeyring) -> None:
    broken = CHECKPOINT_PUBLIC_KEY_FILE.parent / "broken_private.pem"
    broken.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnope\n")
    try:
        rogue = signing.LocalFileSigner(
            broken, CHECKPOINT_PUBLIC_KEY_FILE, CHECKPOINT_KEY_ID, keyring
        )
        with pytest.raises(signing.SigningKeyError, match="not valid pem"):
            rogue.sign(b"payload")
    finally:
        broken.unlink()


def test_private_key_is_loaded_once(signer: signing.LocalFileSigner) -> None:
    signer.sign(b"first")
    loaded = signer._private
    signer.sign(b"second")
    assert signer._private is loaded


def test_verify_only_signer_refuses_to_sign(keyring: signing.PublicKeyring) -> None:
    verifier = signing.VerifyOnlySigner(CHECKPOINT_KEY_ID, keyring)
    with pytest.raises(signing.SigningKeyError, match="signing is not available"):
        verifier.sign(b"payload")


def test_verify_only_signer_verifies_a_real_signature(
    signer: signing.LocalFileSigner, keyring: signing.PublicKeyring
) -> None:
    payload = b"checkpoint-payload"
    signature = signer.sign(payload)
    verifier = signing.VerifyOnlySigner(CHECKPOINT_KEY_ID, keyring)
    assert verifier.verify(payload, signature, CHECKPOINT_KEY_ID) is True


def test_verify_only_signer_rejects_an_unknown_key_id(
    keyring: signing.PublicKeyring,
) -> None:
    verifier = signing.VerifyOnlySigner(CHECKPOINT_KEY_ID, keyring)
    assert verifier.verify(b"payload", bytes(64), "c9") is False


def test_get_signer_returns_a_local_file_signer_when_the_private_key_exists() -> None:
    assert isinstance(signing.get_signer(), signing.LocalFileSigner)


def test_get_signer_is_cached() -> None:
    assert signing.get_signer() is signing.get_signer()


def test_get_keyring_is_cached() -> None:
    assert signing.get_keyring() is signing.get_keyring()


def test_get_signer_degrades_to_verify_only_without_a_private_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    absent = CHECKPOINT_PUBLIC_KEY_FILE.parent / "absent_private.pem"
    monkeypatch.setenv("AUDIT_CHECKPOINT_PRIVATE_KEY_FILE", str(absent))
    get_settings.cache_clear()
    signing.reset_signer_cache()
    assert get_settings().checkpoint_private_key_file == absent
    assert isinstance(signing.get_signer(), signing.VerifyOnlySigner)


def test_reset_signer_cache_clears_both_caches() -> None:
    first_signer = signing.get_signer()
    first_keyring = signing.get_keyring()
    signing.reset_signer_cache()
    assert signing.get_signer() is not first_signer
    assert signing.get_keyring() is not first_keyring


def test_build_checkpoint_payload_is_verifiable_end_to_end(
    signer: signing.LocalFileSigner,
) -> None:
    payload = signing.build_checkpoint_payload(
        key_id=CHECKPOINT_KEY_ID,
        tree_size=12,
        tail_sequence_number=12,
        tail_chain_hash=bytes(range(32)),
        prev_checkpoint_hash=bytes(32),
    )
    signature = signer.sign(payload)
    assert signer.verify(payload, signature, CHECKPOINT_KEY_ID) is True
    assert len(compute_checkpoint_hash(payload)) == 32


def test_a_signature_does_not_transfer_to_a_different_checkpoint(
    signer: signing.LocalFileSigner,
) -> None:
    first = signing.build_checkpoint_payload(CHECKPOINT_KEY_ID, 12, 12, bytes(range(32)), bytes(32))
    second = signing.build_checkpoint_payload(
        CHECKPOINT_KEY_ID, 13, 13, bytes(range(32)), bytes(32)
    )
    assert signer.verify(second, signer.sign(first), CHECKPOINT_KEY_ID) is False
