"""Bundle hashing utilities for v1.5r."""

from __future__ import annotations

from typing import Any

from .canon import canon_bytes, sha256_prefixed, sha256_hex


def bundle_hash(manifest: dict[str, Any], blobs: dict[str, bytes], validate_blobs: bool = True) -> str:
    payload = dict(manifest)
    payload.pop("bundle_hash", None)
    manifest_bytes = canon_bytes(payload)
    parts = [manifest_bytes]
    for blob_hash in sorted(blobs.keys()):
        blob_bytes = blobs[blob_hash]
        if validate_blobs:
            expected = f"sha256:{sha256_hex(blob_bytes)}"
            if blob_hash != expected:
                raise ValueError("blob hash mismatch in bundle")
        parts.append(blob_bytes)
    return sha256_prefixed(b"".join(parts))
