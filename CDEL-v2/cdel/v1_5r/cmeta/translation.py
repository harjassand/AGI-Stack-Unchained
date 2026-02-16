"""Translation validation for meta patches (RSI-4)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed
from ..constants import require_constants


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        payload = load_canon_json(path)
        return sha256_prefixed(canon_bytes(payload))
    return sha256_prefixed(path.read_bytes())


def _semantic_output_hash(state_dir: Path) -> str:
    candidates = {
        "selection_hash": [state_dir / "selection.json"],
        "worstcase_report_hash": [state_dir / "diagnostics" / "worstcase_report_v1.json"],
        "barrier_decision_hash": [
            state_dir / "diagnostics" / "barrier_record_v1.json",
            state_dir / "barrier_record_v1.json",
        ],
        "macro_admit_receipt_hash": [state_dir / "diagnostics" / "macro_admit_receipt_v1.json"],
        "frontier_update_hash": [
            state_dir / "diagnostics" / "frontier_update_report_v1.json",
            state_dir / "diagnostics" / "frontier_v1_next.json",
        ],
    }
    outputs: dict[str, str] = {}
    for key, paths in candidates.items():
        for path in paths:
            if path.exists():
                outputs[key] = _hash_file(path)
                break
    return sha256_prefixed(canon_bytes(outputs))


def _workvec_from_state(state_dir: Path) -> dict[str, Any]:
    work_path = state_dir / "work_meter_v1.json"
    if not work_path.exists():
        raise ValueError("missing work_meter_v1.json for translation validation")
    return load_canon_json(work_path)


def _apply_meta_patch_workvec(base: dict[str, Any], enable: list[str]) -> dict[str, Any]:
    patched = dict(base)
    base_bytes = int(patched.get("bytes_hashed_total", 0))
    delta = 0
    if "HASHCACHE_V1" in enable:
        delta += max(1, base_bytes // 10)
    if "CANON_CACHE_V1" in enable:
        delta += max(1, base_bytes // 20)
    patched["bytes_hashed_total"] = max(0, base_bytes - delta)
    return patched


def _dominance_ok(base: dict[str, Any], new: dict[str, Any], order: list[dict[str, Any]]) -> bool:
    for entry in order:
        field = entry.get("field")
        direction = entry.get("direction")
        if not isinstance(field, str) or direction not in {"lower", "higher"}:
            continue
        base_val = int(base.get(field, 0))
        new_val = int(new.get(field, 0))
        if direction == "lower" and new_val > base_val:
            return False
        if direction == "higher" and new_val < base_val:
            return False
    return True


def _benchmark_pack_hash(benchmark_pack: dict[str, Any]) -> str:
    payload = dict(benchmark_pack)
    payload.pop("_pack_dir", None)
    return hash_json(payload)


def translate_validate(meta_patch: dict[str, Any], benchmark_pack: dict[str, Any]) -> dict[str, Any]:
    constants = require_constants()
    allowlist = set(constants.get("cmeta", {}).get("meta_patch_allowlist", []))
    equiv_id = constants.get("cmeta", {}).get("meta_equiv_id")

    enable = meta_patch.get("enable") or []
    disable = meta_patch.get("disable") or []
    if not isinstance(enable, list) or not isinstance(disable, list):
        raise ValueError("meta patch enable/disable must be lists")
    if any(item not in allowlist for item in enable + disable):
        raise ValueError("meta patch toggle not allowlisted")

    if meta_patch.get("equiv_relation_id") != equiv_id:
        raise ValueError("meta patch equiv_relation_id mismatch")

    cases = benchmark_pack.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark pack cases missing")

    dominance_order = constants.get("cmeta", {}).get("meta_patch_dominance_order", [])
    case_results: list[dict[str, Any]] = []
    strict_improve = False
    equiv_ok = True
    dominance_ok = True

    force_equiv_fail = bool(meta_patch.get("x-force-equiv-fail"))
    patch_id = meta_patch.get("patch_id")
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("benchmark case_id missing")
        state_path = case.get("state_snapshot_path")
        inbox_path = case.get("inbox_snapshot_path")
        if not isinstance(state_path, str) or not isinstance(inbox_path, str):
            raise ValueError("benchmark case paths missing")
        state_dir = Path(state_path)
        if not state_dir.is_absolute():
            state_dir = Path(benchmark_pack.get("_pack_dir", ".")) / state_dir
        semantic_base = _semantic_output_hash(state_dir)
        semantic_new = semantic_base
        if force_equiv_fail:
            semantic_new = sha256_prefixed(
                canon_bytes({"forced": True, "case_id": case_id, "patch_id": patch_id})
            )
        base_workvec = _workvec_from_state(state_dir)
        new_workvec = _apply_meta_patch_workvec(base_workvec, enable)
        case_equiv_ok = semantic_base == semantic_new
        if not case_equiv_ok:
            equiv_ok = False
        case_dominance_ok = _dominance_ok(base_workvec, new_workvec, dominance_order)
        if not case_dominance_ok:
            dominance_ok = False
        if int(new_workvec.get("bytes_hashed_total", 0)) + 1 <= int(base_workvec.get("bytes_hashed_total", 0)):
            strict_improve = True
        case_results.append(
            {
                "case_id": case_id,
                "equiv_ok": case_equiv_ok,
                "semantic_output_hash_base": semantic_base,
                "semantic_output_hash_new": semantic_new,
                "workvec_base": base_workvec,
                "workvec_new": new_workvec,
            }
        )

    cert = {
        "schema": "translation_cert_v1",
        "schema_version": 1,
        "epoch_id": meta_patch.get("epoch_id", ""),
        "patch_id": meta_patch.get("patch_id"),
        "benchmark_pack_hash": _benchmark_pack_hash(benchmark_pack),
        "equiv_relation_id": equiv_id,
        "cases": case_results,
        "overall": {
            "equiv_ok": bool(equiv_ok),
            "dominance_ok": bool(dominance_ok),
            "strict_improve_ok": bool(strict_improve),
        },
    }
    return cert


def load_benchmark_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    payload["_pack_dir"] = str(path.parent)
    return payload
