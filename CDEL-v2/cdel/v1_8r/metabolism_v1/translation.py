"""Translation validation protocol for metabolism v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache_ctx_hash import CtxHashCache, compute_onto_ctx_hash
from .workvec import WorkVec, canon_bytes, lexicographic_strictly_smaller, new_workvec, sha256
from ...v1_7r.canon import CanonError, canon_bytes as base_canon_bytes, load_canon_json, sha256_prefixed


def _require_int(value: Any, *, name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be int")
    return int(value)


def _require_str(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be str")
    return value


def _validate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = _require_str(case.get("case_id"), name="case_id")
    kind = _require_str(case.get("kind"), name="kind")
    if kind != "ctx_hash_repeat_v1":
        raise ValueError("case kind mismatch")
    ctx_mode = _require_str(case.get("ctx_mode"), name="ctx_mode")
    repeat = _require_int(case.get("repeat"), name="repeat")
    if repeat < 1 or repeat > 65536:
        raise ValueError("repeat out of range")

    if ctx_mode == "null":
        allowed = {"case_id", "kind", "ctx_mode", "repeat"}
        extra = set(case.keys()) - allowed
        if extra:
            raise ValueError("null ctx_mode must not include extra fields")
        return {
            "case_id": case_id,
            "kind": kind,
            "ctx_mode": ctx_mode,
            "repeat": repeat,
        }

    if ctx_mode == "explicit":
        ontology_id = _require_str(case.get("active_ontology_id"), name="active_ontology_id")
        snapshot_id = _require_str(case.get("active_snapshot_id"), name="active_snapshot_id")
        values = case.get("values")
        if not isinstance(values, list):
            raise ValueError("values must be list")
        if len(values) > 8:
            raise ValueError("values length out of range")
        for val in values:
            if not isinstance(val, int):
                raise ValueError("values must be int")
            if val < -2147483648 or val > 2147483647:
                raise ValueError("values out of i32 range")
        allowed = {"case_id", "kind", "ctx_mode", "repeat", "active_ontology_id", "active_snapshot_id", "values"}
        extra = set(case.keys()) - allowed
        if extra:
            raise ValueError("explicit ctx_mode must not include extra fields")
        return {
            "case_id": case_id,
            "kind": kind,
            "ctx_mode": ctx_mode,
            "repeat": repeat,
            "active_ontology_id": ontology_id,
            "active_snapshot_id": snapshot_id,
            "values": values,
        }

    raise ValueError("ctx_mode mismatch")


def validate_translation_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "translation_inputs_v1":
        raise ValueError("translation_inputs schema mismatch")
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("translation_inputs schema_version mismatch")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("translation_inputs cases missing")
    validated = [_validate_case(case) for case in cases if isinstance(case, dict)]
    if len(validated) != len(cases):
        raise ValueError("translation_inputs case invalid")
    return {"schema": payload.get("schema"), "schema_version": payload.get("schema_version"), "cases": validated}


def load_translation_inputs(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    return validate_translation_inputs(payload)


def translation_inputs_hash(payload: dict[str, Any]) -> str:
    return sha256_prefixed(base_canon_bytes(payload))


def _ctx_key_obj(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("ctx_mode") == "null":
        return {"schema": "onto_ctx_null_v1", "schema_version": 1}
    return {
        "schema": "onto_ctx_key_v1",
        "schema_version": 1,
        "ontology_id": case.get("active_ontology_id"),
        "snapshot_id": case.get("active_snapshot_id"),
        "values": case.get("values", []),
    }


def _run_case(case: dict[str, Any], *, workvec: WorkVec, cache: CtxHashCache | None) -> str:
    ctx_key_obj = _ctx_key_obj(case)
    repeat = int(case.get("repeat", 0))
    hashes: list[str] = []
    for _ in range(repeat):
        hashes.append(compute_onto_ctx_hash(ctx_key_obj, cache=cache, workvec=workvec))
    output_obj = {
        "schema": "translation_case_output_v1",
        "schema_version": 1,
        "case_id": case.get("case_id"),
        "hashes": hashes,
    }
    output_bytes = canon_bytes(output_obj, workvec)
    return sha256(output_bytes, workvec)


def run_translation(
    translation_inputs: dict[str, Any], *, cache_capacity: int | None
) -> tuple[list[dict[str, str]], WorkVec]:
    workvec = new_workvec()
    cache = None
    if cache_capacity is not None:
        cache = CtxHashCache(cache_capacity)
        cache.reset()
    results: list[dict[str, str]] = []
    for case in translation_inputs.get("cases", []):
        output_hash = _run_case(case, workvec=workvec, cache=cache)
        results.append({"case_id": case.get("case_id"), "output_hash": output_hash})
    return results, workvec


def evaluate_translation(
    *,
    translation_inputs: dict[str, Any],
    cache_capacity: int,
    min_sha256_delta: int,
) -> dict[str, Any]:
    base_results, workvec_base = run_translation(translation_inputs, cache_capacity=None)
    patch_results, workvec_patch = run_translation(translation_inputs, cache_capacity=cache_capacity)

    if len(base_results) != len(patch_results):
        raise CanonError("translation case count mismatch")

    translation_results: list[dict[str, Any]] = []
    equal_all = True
    for base, patch in zip(base_results, patch_results):
        case_id = base.get("case_id")
        if case_id != patch.get("case_id"):
            raise CanonError("translation case_id mismatch")
        base_hash = base.get("output_hash")
        patch_hash = patch.get("output_hash")
        equal = base_hash == patch_hash
        if not equal:
            equal_all = False
        translation_results.append(
            {
                "case_id": case_id,
                "base_output_hash": base_hash,
                "patch_output_hash": patch_hash,
                "equal": bool(equal),
            }
        )

    dominance_ok = lexicographic_strictly_smaller(workvec_patch, workvec_base)
    sha256_delta = int(workvec_base.sha256_calls_total) - int(workvec_patch.sha256_calls_total)
    min_delta_ok = sha256_delta >= int(min_sha256_delta)

    passes = bool(equal_all and dominance_ok and min_delta_ok)
    if not equal_all:
        reason = "output_hash mismatch"
    elif not dominance_ok:
        reason = "workvec dominance failed"
    elif not min_delta_ok:
        reason = "sha256 delta below minimum"
    else:
        reason = "ok"

    return {
        "translation_results": translation_results,
        "workvec_base": workvec_base,
        "workvec_patch": workvec_patch,
        "decision": {"passes": passes, "reason": reason},
    }
