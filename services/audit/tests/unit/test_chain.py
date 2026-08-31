from __future__ import annotations

import hashlib

import pytest

from app.core import chain

pytestmark = pytest.mark.unit


def _sha256(*parts: bytes) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.digest()


def _prefixed(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def test_leaf_hash_matches_specification() -> None:
    payload = b"audit-event-payload"
    expected = _sha256(b"\x00", _prefixed(payload))
    assert chain.compute_leaf_hash(payload) == expected


def test_leaf_hash_golden_vector() -> None:
    assert chain.compute_leaf_hash(b"").hex() == (
        "3e7077fd2f66d689e0cee6a7cf5b37bf2dca7c979af356d0a31cbc5c85605c7d"
    )


def test_leaf_hash_is_domain_separated_from_plain_sha256() -> None:
    payload = b"audit-event-payload"
    assert chain.compute_leaf_hash(payload) != hashlib.sha256(payload).digest()


def test_leaf_hash_length_prefix_prevents_ambiguity() -> None:
    assert chain.compute_leaf_hash(b"ab") != chain.compute_leaf_hash(b"a") + b"b"


def test_chain_hash_matches_specification() -> None:
    prev = bytes(range(32))
    leaf = bytes(range(32, 64))
    expected = _sha256(b"\x01", prev, leaf)
    assert chain.compute_chain_hash(prev, leaf) == expected


def test_chain_hash_differs_from_leaf_domain() -> None:
    prev = bytes(32)
    leaf = bytes(range(32, 64))
    assert chain.compute_chain_hash(prev, leaf) != _sha256(b"\x00", prev, leaf)


@pytest.mark.parametrize("width", [0, 31, 33, 64])
def test_chain_hash_rejects_wrong_prev_width(width: int) -> None:
    with pytest.raises(ValueError, match="prev_hash must be 32 bytes"):
        chain.compute_chain_hash(bytes(width), bytes(32))


@pytest.mark.parametrize("width", [0, 31, 33, 64])
def test_chain_hash_rejects_wrong_leaf_width(width: int) -> None:
    with pytest.raises(ValueError, match="leaf_hash must be 32 bytes"):
        chain.compute_chain_hash(bytes(32), bytes(width))


def test_genesis_hashes_are_thirty_two_zero_bytes() -> None:
    assert chain.genesis_prev_hash() == bytes(32)
    assert chain.genesis_checkpoint_hash() == bytes(32)
    assert bytes(32) == chain.GENESIS_PREV_HASH
    assert bytes(32) == chain.GENESIS_CHECKPOINT_HASH


def test_digest_size_of_sha256() -> None:
    assert chain.digest_size(chain.HASH_ALGORITHM_SHA256) == 32


@pytest.mark.parametrize("algorithm", [0, 2, -1, 99])
def test_digest_size_rejects_unknown_algorithm(algorithm: int) -> None:
    with pytest.raises(chain.UnsupportedAlgorithmError):
        chain.digest_size(algorithm)


def test_is_supported_only_accepts_sha256() -> None:
    assert chain.is_supported(chain.HASH_ALGORITHM_SHA256) is True
    assert chain.is_supported(chain.HASH_ALGORITHM_UNSPECIFIED) is False
    assert chain.is_supported(2) is False


def test_default_algorithm_is_sha256() -> None:
    assert chain.DEFAULT_HASH_ALGORITHM == chain.HASH_ALGORITHM_SHA256


def test_unsupported_algorithm_rejected_on_leaf_hash() -> None:
    with pytest.raises(chain.UnsupportedAlgorithmError):
        chain.compute_leaf_hash(b"payload", 2)


def test_leaf_matches_accepts_true_hash() -> None:
    payload = b"payload"
    assert chain.leaf_matches(payload, chain.compute_leaf_hash(payload)) is True


def test_leaf_matches_rejects_altered_payload() -> None:
    leaf = chain.compute_leaf_hash(b"payload")
    assert chain.leaf_matches(b"payload-tampered", leaf) is False


def test_leaf_matches_rejects_truncated_hash() -> None:
    payload = b"payload"
    truncated = chain.compute_leaf_hash(payload)[:16]
    assert chain.leaf_matches(payload, truncated) is False


def test_chain_matches_accepts_true_link() -> None:
    prev = bytes(32)
    leaf = chain.compute_leaf_hash(b"payload")
    linked = chain.compute_chain_hash(prev, leaf)
    assert chain.chain_matches(prev, leaf, linked) is True


def test_chain_matches_rejects_relinked_predecessor() -> None:
    leaf = chain.compute_leaf_hash(b"payload")
    linked = chain.compute_chain_hash(bytes(32), leaf)
    assert chain.chain_matches(bytes(range(32)), leaf, linked) is False


def test_checkpoint_payload_matches_specification() -> None:
    tail = bytes(range(32))
    prev = bytes(range(32, 64))
    expected = b"".join(
        [
            b"\x02",
            (1).to_bytes(8, "big"),
            (1).to_bytes(8, "big"),
            _prefixed(b"c1"),
            (7).to_bytes(8, "big"),
            (7).to_bytes(8, "big"),
            _prefixed(tail),
            _prefixed(prev),
        ]
    )
    assert (
        chain.checkpoint_payload(
            key_id="c1",
            tree_size=7,
            tail_sequence_number=7,
            tail_chain_hash=tail,
            prev_checkpoint_hash=prev,
            signature_algorithm=1,
        )
        == expected
    )


def test_checkpoint_payload_separates_key_id_from_following_fields() -> None:
    tail = bytes(32)
    prev = bytes(32)
    first = chain.checkpoint_payload("c1", 1, 1, tail, prev, 1)
    second = chain.checkpoint_payload("c", 1, 1, tail, prev, 1)
    assert first != second


def test_checkpoint_payload_binds_signature_algorithm() -> None:
    tail = bytes(32)
    prev = bytes(32)
    assert chain.checkpoint_payload("c1", 1, 1, tail, prev, 1) != chain.checkpoint_payload(
        "c1", 1, 1, tail, prev, 2
    )


def test_checkpoint_payload_binds_tree_size_and_tail_sequence() -> None:
    tail = bytes(32)
    prev = bytes(32)
    assert chain.checkpoint_payload("c1", 2, 1, tail, prev, 1) != chain.checkpoint_payload(
        "c1", 1, 2, tail, prev, 1
    )


@pytest.mark.parametrize("width", [0, 31, 33])
def test_checkpoint_payload_rejects_wrong_tail_width(width: int) -> None:
    with pytest.raises(ValueError, match="tail_chain_hash must be 32 bytes"):
        chain.checkpoint_payload("c1", 1, 1, bytes(width), bytes(32), 1)


@pytest.mark.parametrize("width", [0, 31, 33])
def test_checkpoint_payload_rejects_wrong_prev_width(width: int) -> None:
    with pytest.raises(ValueError, match="prev_checkpoint_hash must be 32 bytes"):
        chain.checkpoint_payload("c1", 1, 1, bytes(32), bytes(width), 1)


def test_checkpoint_payload_rejects_negative_tree_size() -> None:
    with pytest.raises(ValueError, match="out of range for uint64"):
        chain.checkpoint_payload("c1", -1, 1, bytes(32), bytes(32), 1)


def test_checkpoint_payload_rejects_tree_size_above_uint64() -> None:
    with pytest.raises(ValueError, match="out of range for uint64"):
        chain.checkpoint_payload("c1", 2**64, 1, bytes(32), bytes(32), 1)


def test_checkpoint_payload_accepts_uint64_maximum() -> None:
    payload = chain.checkpoint_payload("c1", 2**64 - 1, 1, bytes(32), bytes(32), 1)
    assert b"\xff" * 8 in payload


def test_checkpoint_hash_matches_specification() -> None:
    payload = chain.checkpoint_payload("c1", 1, 1, bytes(32), bytes(32), 1)
    assert chain.compute_checkpoint_hash(payload) == _sha256(b"\x03", _prefixed(payload))


def test_checkpoint_hash_domain_differs_from_payload_domain() -> None:
    payload = chain.checkpoint_payload("c1", 1, 1, bytes(32), bytes(32), 1)
    assert chain.compute_checkpoint_hash(payload) != _sha256(b"\x02", _prefixed(payload))


def test_checkpoint_matches_accepts_true_hash() -> None:
    payload = chain.checkpoint_payload("c1", 1, 1, bytes(32), bytes(32), 1)
    assert chain.checkpoint_matches(payload, chain.compute_checkpoint_hash(payload)) is True


def test_checkpoint_matches_rejects_altered_payload() -> None:
    payload = chain.checkpoint_payload("c1", 1, 1, bytes(32), bytes(32), 1)
    other = chain.checkpoint_payload("c1", 2, 1, bytes(32), bytes(32), 1)
    assert chain.checkpoint_matches(other, chain.compute_checkpoint_hash(payload)) is False


def test_key_id_is_utf8_encoded_in_payload() -> None:
    payload = chain.checkpoint_payload("kéy", 1, 1, bytes(32), bytes(32), 1)
    assert _prefixed("kéy".encode()) in payload
