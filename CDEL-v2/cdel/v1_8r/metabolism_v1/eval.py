"""Metabolism v1 evaluation + ledger updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, hash_json, load_canon_json, write_canon_json
from ..constants import meta_identities
from .io import compute_patch_id, ensure_metabolism_dirs, patch_def_hash, write_patch_def_if_missing
from .ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries
from .translation import evaluate_translation, translation_inputs_hash, validate_translation_inputs


def _epoch_index(epoch_id: str) -> int | None:
    tail = str(epoch_id).split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _meta_check(payload: dict[str, Any], meta: dict[str, str]) -> None:
    xmeta = payload.get("x-meta")
    if not isinstance(xmeta, dict):
        raise CanonError("x-meta missing")
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash"):
        if xmeta.get(key) != meta.get(key):
            raise CanonError("x-meta mismatch")


def _validate_patch_def(patch_def: dict[str, Any], constants: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    if patch_def.get("schema") != "meta_patch_def_v1":
        raise CanonError("meta patch def schema mismatch")
    if int(patch_def.get("schema_version", 0)) != 1:
        raise CanonError("meta patch def schema_version mismatch")
    _meta_check(patch_def, meta)
    patch_id = patch_def.get("patch_id")
    if not isinstance(patch_id, str):
        raise CanonError("patch_id missing")
    expected = compute_patch_id(patch_def)
    if patch_id != expected:
        raise CanonError("patch_id mismatch")
    patch_kind = patch_def.get("patch_kind")
    if patch_kind != "ctx_hash_cache_v1":
        raise CanonError("patch_kind not allowlisted")
    params = patch_def.get("params") if isinstance(patch_def.get("params"), dict) else {}
    capacity = int(params.get("capacity", 0))
    max_capacity = int(constants.get("CTX_HASH_CACHE_V1_MAX_CAPACITY", 0) or 0)
    if capacity < 1 or capacity > max_capacity:
        raise CanonError("capacity out of range")
    return patch_def


def _write_active_set(path: Path, patch_id: str, epoch_idx: int, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "meta_patch_active_set_v1",
        "schema_version": 1,
        "active_patch_ids": [patch_id],
        "activation_epoch": int(epoch_idx),
        "x-meta": meta,
    }
    write_canon_json(path, payload)
    return payload


def evaluate_epoch(
    *,
    state_dir: Path,
    epoch_id: str,
    constants: dict[str, Any],
    proposals: list[dict[str, Any]],
    translation_inputs: dict[str, Any],
    strict: bool = True,
) -> dict[str, Any] | None:
    meta = meta_identities()
    metabolism_root = state_dir / "current" / "metabolism_v1"
    dirs = ensure_metabolism_dirs(metabolism_root)
    ledger_path = dirs["ledger"] / "meta_patch_ledger_v1.jsonl"
    active_path = dirs["active"] / "meta_patch_active_set_v1.json"

    epoch_idx = _epoch_index(epoch_id)
    if epoch_idx is None:
        raise CanonError("invalid epoch_id")

    translation_inputs = validate_translation_inputs(translation_inputs)
    inputs_hash = translation_inputs_hash(translation_inputs)

    best = None
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        try:
            patch_def = _validate_patch_def(proposal, constants, meta)
            patch_id = patch_def.get("patch_id")
            patch_hash = patch_def_hash(patch_def)
            capacity = int(patch_def.get("params", {}).get("capacity", 0))
            eval_result = evaluate_translation(
                translation_inputs=translation_inputs,
                cache_capacity=capacity,
                min_sha256_delta=int(constants.get("METAPATCH_V1_MIN_SHA256_CALL_DELTA", 0) or 0),
            )
            decision = eval_result.get("decision", {})
            if not bool(decision.get("passes")):
                continue
            candidate = {
                "patch_def": patch_def,
                "patch_id": patch_id,
                "patch_def_hash": patch_hash,
                "translation_results": eval_result.get("translation_results", []),
                "workvec_base": eval_result.get("workvec_base"),
                "workvec_patch": eval_result.get("workvec_patch"),
                "decision": decision,
            }
            if best is None:
                best = candidate
            else:
                best_workvec = best.get("workvec_patch")
                cand_workvec = candidate.get("workvec_patch")
                if best_workvec is None or cand_workvec is None:
                    continue
                cand_tuple = (
                    int(cand_workvec.sha256_calls_total),
                    int(cand_workvec.canon_calls_total),
                    int(cand_workvec.sha256_bytes_total),
                    int(cand_workvec.canon_bytes_total),
                    int(cand_workvec.onto_ctx_hash_compute_calls_total),
                )
                best_tuple = (
                    int(best_workvec.sha256_calls_total),
                    int(best_workvec.canon_calls_total),
                    int(best_workvec.sha256_bytes_total),
                    int(best_workvec.canon_bytes_total),
                    int(best_workvec.onto_ctx_hash_compute_calls_total),
                )
                if cand_tuple < best_tuple:
                    best = candidate
                elif cand_tuple == best_tuple:
                    if str(candidate.get("patch_id")) < str(best.get("patch_id")):
                        best = candidate
        except Exception:
            if strict:
                continue
            continue

    if best is None:
        return None

    patch_def = best["patch_def"]
    patch_id = best["patch_id"]
    patch_hash = best["patch_def_hash"]

    write_patch_def_if_missing(patch_def, dirs["defs"])

    report = {
        "schema": "meta_patch_eval_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "patch_id": patch_id,
        "patch_def_hash": patch_hash,
        "translation_inputs_hash": inputs_hash,
        "translation_results": best["translation_results"],
        "workvec_base": best["workvec_base"].to_dict(),
        "workvec_patch": best["workvec_patch"].to_dict(),
        "decision": best["decision"],
        "x-meta": meta,
    }
    report_path = dirs["reports"] / f"meta_patch_eval_report_v1_epoch_{epoch_idx}.json"
    write_canon_json(report_path, report)
    report_hash = hash_json(report)

    admit_receipt = {
        "schema": "meta_patch_admit_receipt_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "patch_id": patch_id,
        "patch_def_hash": patch_hash,
        "meta_patch_eval_report_hash": report_hash,
        "verdict": "VALID",
        "x-meta": meta,
    }
    receipt_path = dirs["receipts"] / f"meta_patch_admit_receipt_v1_epoch_{epoch_idx}.json"
    write_canon_json(receipt_path, admit_receipt)
    receipt_hash = hash_json(admit_receipt)

    ledger_entries = load_ledger_entries(ledger_path)
    prev_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

    admit_entry = build_ledger_entry(
        event="ADMIT",
        epoch_id=epoch_id,
        patch_id=patch_id,
        patch_def_hash=patch_hash,
        meta_patch_admit_receipt_hash=receipt_hash,
        prev_line_hash=prev_hash,
        meta=meta,
    )
    append_ledger_entry(ledger_path, admit_entry)

    activate_entry = build_ledger_entry(
        event="ACTIVATE",
        epoch_id=epoch_id,
        patch_id=patch_id,
        patch_def_hash=None,
        meta_patch_admit_receipt_hash=None,
        prev_line_hash=admit_entry.get("line_hash"),
        meta=meta,
    )
    append_ledger_entry(ledger_path, activate_entry)

    _write_active_set(active_path, patch_id, epoch_idx, meta)

    return {
        "report": report,
        "admit_receipt": admit_receipt,
        "ledger_entries": [admit_entry, activate_entry],
        "active_set": load_canon_json(active_path),
    }
