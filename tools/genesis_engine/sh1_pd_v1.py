#!/usr/bin/env python3
"""SH-1 proposal descriptor extraction for PATCH CCAP payloads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes


_ZERO_SHA = "sha256:" + ("0" * 64)


def _invalid(reason: str) -> RuntimeError:
    msg = reason
    if not msg.startswith("INVALID:"):
        msg = f"INVALID:{msg}"
    return RuntimeError(msg)


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise _invalid("SCHEMA_FAIL")
    return rel


def touched_paths_from_patch_bytes(patch_bytes: bytes) -> list[str]:
    try:
        text = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("SCHEMA_FAIL") from exc
    paths: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line.startswith("+++ b/"):
            continue
        tail = line[len("+++ b/") :]
        # git-style headers are path-only; tolerate optional tab suffix deterministically.
        rel = tail.split("\t", 1)[0]
        paths.add(_normalize_relpath(rel))
    return sorted(paths)


def touched_paths_hash_for_paths(paths: list[str]) -> str:
    normalized = [_normalize_relpath(row) for row in paths]
    payload = {"paths": sorted(normalized)}
    return _sha256_prefixed(canon_bytes(payload))


def size_bucket_u8_for_bytes(size_bytes_u64: int, thresholds: list[int]) -> int:
    if int(size_bytes_u64) < 0:
        raise _invalid("SCHEMA_FAIL")
    out_thresholds: list[int] = []
    for row in thresholds:
        value = int(row)
        if value <= 0:
            raise _invalid("SCHEMA_FAIL")
        out_thresholds.append(value)
    for idx, threshold in enumerate(out_thresholds):
        if int(size_bytes_u64) <= int(threshold):
            return int(idx)
    return int(len(out_thresholds))


def extract_patch_features(*, patch_bytes: bytes, size_buckets_bytes_u64: list[int]) -> dict[str, Any]:
    touched_paths = touched_paths_from_patch_bytes(patch_bytes)
    touched_paths_hash = touched_paths_hash_for_paths(touched_paths)
    size_bucket_u8 = size_bucket_u8_for_bytes(len(patch_bytes), size_buckets_bytes_u64)
    return {
        "touched_paths": touched_paths,
        "touched_paths_hash": touched_paths_hash,
        "size_bucket_u8": int(size_bucket_u8),
    }


def touched_paths_hash_prefix_hex(*, touched_paths_hash: str, prefix_hex_u8: int) -> str:
    digest = str(touched_paths_hash).strip()
    if not digest.startswith("sha256:"):
        raise _invalid("SCHEMA_FAIL")
    hexd = digest.split(":", 1)[1]
    if len(hexd) != 64:
        raise _invalid("SCHEMA_FAIL")
    count = max(0, min(64, int(prefix_hex_u8)))
    return hexd[:count]


def pd_without_id(
    *,
    base_tree_id: str,
    ek_id: str,
    op_pool_id: str,
    touched_paths_hash: str,
    size_bucket_u8: int,
) -> dict[str, Any]:
    return {
        "schema_version": "ge_pd_v1",
        "kind": "PATCH",
        "base_tree_id": str(base_tree_id).strip() or _ZERO_SHA,
        "ek_id": str(ek_id).strip() or _ZERO_SHA,
        "op_pool_id": str(op_pool_id).strip() or _ZERO_SHA,
        "touched_paths_hash": str(touched_paths_hash).strip() or _ZERO_SHA,
        "size_bucket_u8": int(size_bucket_u8),
    }


def pd_id_from_pd_no_id(pd_no_id: dict[str, Any]) -> str:
    return _sha256_prefixed(canon_bytes(pd_no_id))


def build_pd_from_patch_bytes(
    *,
    patch_bytes: bytes,
    base_tree_id: str,
    ek_id: str,
    op_pool_id: str,
    size_buckets_bytes_u64: list[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    features = extract_patch_features(
        patch_bytes=patch_bytes,
        size_buckets_bytes_u64=size_buckets_bytes_u64,
    )
    pd_no_id = pd_without_id(
        base_tree_id=base_tree_id,
        ek_id=ek_id,
        op_pool_id=op_pool_id,
        touched_paths_hash=str(features["touched_paths_hash"]),
        size_bucket_u8=int(features["size_bucket_u8"]),
    )
    pd_payload = {
        "schema_version": "ge_pd_v1",
        "pd_id": pd_id_from_pd_no_id(pd_no_id),
        "kind": "PATCH",
        "base_tree_id": pd_no_id["base_tree_id"],
        "ek_id": pd_no_id["ek_id"],
        "op_pool_id": pd_no_id["op_pool_id"],
        "touched_paths_hash": pd_no_id["touched_paths_hash"],
        "size_bucket_u8": pd_no_id["size_bucket_u8"],
    }
    return pd_payload, features


__all__ = [
    "build_pd_from_patch_bytes",
    "extract_patch_features",
    "pd_id_from_pd_no_id",
    "pd_without_id",
    "size_bucket_u8_for_bytes",
    "touched_paths_from_patch_bytes",
    "touched_paths_hash_for_paths",
    "touched_paths_hash_prefix_hex",
]
