"""Autonomy enumerator helpers for v2.0."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v1_8r.metabolism_v1.translation import validate_translation_inputs
from ..v1_8r.metabolism_v1.ledger import self_hash
from .constants import meta_identities, require_constants


def translation_inputs_hash(translation_inputs: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(translation_inputs))


def constants_hash(constants: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(constants))


def _ctx_key(case: dict[str, Any]) -> tuple[Any, ...]:
    ctx_mode = case.get("ctx_mode")
    if ctx_mode == "null":
        return ("NULL_V1",)
    if ctx_mode == "explicit":
        ontology_id = case.get("active_ontology_id")
        snapshot_id = case.get("active_snapshot_id")
        values = case.get("values")
        values_tuple = tuple(values) if isinstance(values, list) else tuple()
        return ("KEY_V1", ontology_id, snapshot_id, values_tuple)
    raise CanonError("invalid ctx_mode")


def _next_pow2(n: int) -> int:
    if n <= 1:
        return 1
    value = 1
    while value < n:
        value <<= 1
    return value


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _highest_power_of_two_leq(n: int) -> int:
    if n <= 1:
        return 1
    value = 1
    while value << 1 <= n:
        value <<= 1
    return value


def _capacity_for_attempt(*, u: int, max_cap: int, start_shift: int, attempt_index: int) -> int:
    if u <= 0:
        raise CanonError("translation inputs key set empty")
    p = _next_pow2(u)
    base_cap = min(p, max_cap)
    e = int(attempt_index) - 1 - int(start_shift)
    if e >= 0:
        cap = base_cap * (2**e)
    else:
        cap = base_cap // (2 ** (-e))
    if cap < 1:
        cap = 1
    if cap > max_cap:
        cap = max_cap
        if not _is_power_of_two(max_cap):
            cap = _highest_power_of_two_leq(max_cap)
    return int(cap)


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


def compute_expected(
    translation_inputs: dict[str, Any],
    *,
    attempt_index: int,
    prior_attempt_index: int,
    prior_verifier_reason: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    constants = require_constants()
    meta = meta_identities()
    max_cap = int(constants.get("CTX_HASH_CACHE_V1_MAX_CAPACITY", 0) or 0)
    start_shift = int(constants.get("AUTOPATCH_ENUM_V2_START_SHIFT", 0) or 0)

    validated = validate_translation_inputs(translation_inputs)
    cases = validated.get("cases", [])
    if not isinstance(cases, list):
        raise CanonError("translation inputs cases missing")
    keys = {_ctx_key(case) for case in cases}
    u = len(keys)
    if u <= 0:
        raise CanonError("translation inputs key set empty")

    capacity = _capacity_for_attempt(u=u, max_cap=max_cap, start_shift=start_shift, attempt_index=attempt_index)
    const_hash = constants_hash(constants)

    patch_def = build_patch_def(capacity, meta=meta, constants_hash_value=const_hash)
    patch_def_hash = sha256_prefixed(canon_bytes(patch_def))

    patch_entry = {
        "patch_id": patch_def.get("patch_id"),
        "patch_def_hash": patch_def_hash,
        "patch_kind": patch_def.get("patch_kind"),
        "params": {"capacity": int(capacity)},
    }

    manifest = {
        "schema": "autonomy_manifest_v2",
        "schema_version": 2,
        "autonomy_kind": "metabolism_autonomy_v2",
        "algorithm": "autopatch_enum_v2",
        "attempt_index": int(attempt_index),
        "prior_attempt_index": int(prior_attempt_index),
        "prior_verifier_reason": str(prior_verifier_reason),
        "translation_inputs_hash": translation_inputs_hash(translation_inputs),
        "constants_hash": const_hash,
        "output_subdir": "autonomy/metabolism_v1/proposals",
        "patches": [patch_entry],
        "x-meta": {"KERNEL_HASH": meta.get("KERNEL_HASH"), "META_HASH": meta.get("META_HASH")},
    }
    return manifest, [patch_def]


def load_translation_inputs(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    return validate_translation_inputs(payload)


def write_autonomy_outputs(
    *,
    run_dir: Path,
    translation_inputs: dict[str, Any],
    attempt_index: int,
    prior_attempt_index: int,
    prior_verifier_reason: str,
) -> dict[str, Any]:
    manifest, patch_defs = compute_expected(
        translation_inputs,
        attempt_index=attempt_index,
        prior_attempt_index=prior_attempt_index,
        prior_verifier_reason=prior_verifier_reason,
    )
    proposals_dir = run_dir / "autonomy" / "metabolism_v1" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    for patch_def in patch_defs:
        patch_id = patch_def.get("patch_id")
        hex_part = patch_id.split(":", 1)[1] if isinstance(patch_id, str) and ":" in patch_id else patch_id
        if not isinstance(hex_part, str):
            raise CanonError("invalid patch_id")
        out_path = proposals_dir / f"{hex_part}.json"
        out_path.write_bytes(canon_bytes(patch_def) + b"\n")

    manifest_path = run_dir / "autonomy" / "metabolism_v1" / "autonomy_manifest_v2.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canon_bytes(manifest) + b"\n")
    return manifest
