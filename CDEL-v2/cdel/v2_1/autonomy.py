"""Autonomy helpers for v2.1 (metabolism patches)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from ..v1_8r.metabolism_v1.ledger import self_hash
from ..v1_8r.metabolism_v1.translation import validate_translation_inputs
from .constants import meta_identities, require_constants


def translation_inputs_hash(translation_inputs: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(translation_inputs))


def constants_hash(constants: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(constants))


def build_patch_def(capacity: int, *, meta: dict[str, str], constants_hash_value: str) -> dict[str, Any]:
    patch_def = {
        "schema": "meta_patch_def_v1",
        "schema_version": 1,
        "patch_id": "__SELF__",
        "patch_kind": "ctx_hash_cache_v1",
        "params": {"capacity": int(capacity)},
        "x-meta": {
            "KERNEL_HASH": meta.get("KERNEL_HASH"),
            "META_HASH": meta.get("META_HASH"),
            "constants_hash": constants_hash_value,
        },
    }
    patch_def["patch_id"] = self_hash(patch_def, "patch_id")
    return patch_def


def write_metabolism_patch(
    *,
    run_dir: Path,
    translation_inputs: dict[str, Any],
    attempt_index: int,
    prior_attempt_index: int,
    prior_verifier_reason: str,
    capacity: int,
) -> dict[str, Any]:
    constants = require_constants()
    meta = meta_identities()
    const_hash = constants_hash(constants)

    validated = validate_translation_inputs(translation_inputs)

    patch_def = build_patch_def(capacity, meta=meta, constants_hash_value=const_hash)
    patch_def_hash = sha256_prefixed(canon_bytes(patch_def))

    manifest = {
        "schema": "autonomy_manifest_v2",
        "schema_version": 2,
        "autonomy_kind": "metabolism_autonomy_v2",
        "algorithm": "autopatch_enum_v3",
        "attempt_index": int(attempt_index),
        "prior_attempt_index": int(prior_attempt_index),
        "prior_verifier_reason": str(prior_verifier_reason),
        "translation_inputs_hash": translation_inputs_hash(validated),
        "constants_hash": const_hash,
        "output_subdir": "autonomy/metabolism_v1/proposals",
        "patches": [
            {
                "patch_id": patch_def.get("patch_id"),
                "patch_def_hash": patch_def_hash,
                "patch_kind": patch_def.get("patch_kind"),
                "params": {"capacity": int(capacity)},
            }
        ],
        "x-meta": {"KERNEL_HASH": meta.get("KERNEL_HASH"), "META_HASH": meta.get("META_HASH")},
    }

    proposals_dir = run_dir / "autonomy" / "metabolism_v1" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    patch_id = patch_def.get("patch_id")
    hex_part = patch_id.split(":", 1)[1] if isinstance(patch_id, str) and ":" in patch_id else patch_id
    out_path = proposals_dir / f"{hex_part}.json"
    out_path.write_bytes(canon_bytes(patch_def) + b"\n")

    manifest_path = run_dir / "autonomy" / "metabolism_v1" / "autonomy_manifest_v2.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canon_bytes(manifest) + b"\n")
    return manifest


def load_translation_inputs(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    return validate_translation_inputs(payload)


__all__ = ["load_translation_inputs", "write_metabolism_patch"]
