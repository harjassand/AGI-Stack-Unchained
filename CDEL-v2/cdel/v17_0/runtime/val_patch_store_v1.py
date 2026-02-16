"""Patch manifest ingestion and validation for VAL v17.0."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed


class ValPatchStoreError(ValueError):
    pass


REQUIRED_ABI = {
    "arg0": "state_ptr",
    "arg1": "blocks_ptr",
    "arg2": "blocks_len",
}


def recompute_patch_id(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("patch_id", None)
    return sha256_prefixed(canon_bytes(payload))


def decode_code_bytes(manifest: dict[str, Any]) -> bytes:
    raw = base64.b64decode(str(manifest.get("code_bytes_b64", "")), validate=True)
    if not raw:
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    return raw


def validate_patch_manifest(manifest: dict[str, Any], *, max_code_bytes: int) -> None:
    required = {
        "schema_version",
        "patch_id",
        "target_arch",
        "target_simd",
        "target_feature_set",
        "microkernel_id",
        "code_bytes_b64",
        "entry_offset_u32",
        "declared_code_len_u32",
        "abi",
        "declared_loop_form",
        "declared_mem_access_form",
        "build_receipt_hash",
        "notes",
    }
    if set(manifest.keys()) != required:
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")

    if manifest.get("schema_version") != "val_patch_manifest_v1":
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("target_arch") != "aarch64":
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("target_simd") != "neon128":
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("entry_offset_u32") != 0:
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("declared_loop_form") not in {"COUNTED_LOOP_SUBS_BNE", "FIXED_ROUND"}:
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("declared_mem_access_form") != "STATE32_AND_BLOCKS64_POSTINC":
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if manifest.get("notes") != "":
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")

    abi = manifest.get("abi")
    if not isinstance(abi, dict) or abi != REQUIRED_ABI:
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")

    code_bytes = decode_code_bytes(manifest)
    declared_len = int(manifest.get("declared_code_len_u32", -1))
    if declared_len != len(code_bytes):
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    if declared_len > int(max_code_bytes):
        raise ValPatchStoreError("INVALID:UNSAFE_PRECONDITION_FAIL")

    patch_id = str(manifest.get("patch_id", ""))
    if patch_id != recompute_patch_id(manifest):
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")


def load_patch_manifest(path: Path, *, max_code_bytes: int) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        raise ValPatchStoreError("INVALID:SCHEMA_FAIL")
    validate_patch_manifest(obj, max_code_bytes=max_code_bytes)
    return obj


__all__ = [
    "ValPatchStoreError",
    "decode_code_bytes",
    "load_patch_manifest",
    "recompute_patch_id",
    "validate_patch_manifest",
]
