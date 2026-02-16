import pytest

from cdel.v1_5r.bundle import bundle_hash
from cdel.v1_5r.canon import sha256_prefixed


def test_bundle_hash_deterministic() -> None:
    blob = b"payload"
    blob_hash = sha256_prefixed(blob)
    manifest = {"schema": "bundle_manifest_v1", "schema_version": 1, "blobs": [blob_hash]}
    assert bundle_hash(manifest, {blob_hash: blob}) == bundle_hash(manifest, {blob_hash: blob})


def test_bundle_hash_rejects_mismatch() -> None:
    blob = b"payload"
    blob_hash = sha256_prefixed(blob)
    manifest = {"schema": "bundle_manifest_v1", "schema_version": 1, "blobs": [blob_hash]}
    with pytest.raises(ValueError):
        bundle_hash(manifest, {"sha256:" + "0" * 64: blob})
