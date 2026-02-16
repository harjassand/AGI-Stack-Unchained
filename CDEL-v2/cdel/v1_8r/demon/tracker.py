"""Final receipt tracker for RSI demon v4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, load_canon_json, write_canon_json
from ...v1_7r.ontology_v3.ledger import load_ledger_entries as load_ontology_ledger
from ...v1_7r.macros_v2.ledger import load_ledger_entries as load_macro_ledger
from ..constants import meta_identities, require_constants
from ..metabolism_v1.ledger import load_ledger_entries as load_metabolism_ledger


def _latest_report(path: Path, prefix: str) -> dict[str, Any]:
    if not path.exists():
        raise CanonError(f"missing reports dir: {path}")
    best_epoch = None
    best_path = None
    for report_path in path.glob(f"{prefix}_epoch_*.json"):
        tail = report_path.stem.split("_epoch_")[-1]
        if not tail.isdigit():
            continue
        idx = int(tail)
        if best_epoch is None or idx > best_epoch:
            best_epoch = idx
            best_path = report_path
    if best_path is None:
        raise CanonError("missing reports")
    return load_canon_json(best_path)


def build_receipt(*, state_dir: Path, run_id: str, final_epoch: int) -> dict[str, Any]:
    meta = meta_identities()
    constants = require_constants()

    ontology_root = state_dir / "current" / "ontology_v3"
    macro_root = state_dir / "current" / "macros_v2"
    metabolism_root = state_dir / "current" / "metabolism_v1"

    ontology_ledger = load_ontology_ledger(ontology_root / "ledger" / "ontology_ledger_v3.jsonl")
    macro_ledger = load_macro_ledger(macro_root / "ledger" / "macro_ledger_v2.jsonl")
    metabolism_ledger = load_metabolism_ledger(metabolism_root / "ledger" / "meta_patch_ledger_v1.jsonl")

    ontology_admitted = sum(1 for entry in ontology_ledger if entry.get("event") == "ADMIT")
    ontology_activated = sum(1 for entry in ontology_ledger if entry.get("event") == "ACTIVATE")
    ontology_evicted = sum(1 for entry in ontology_ledger if entry.get("event") == "EVICT")

    macro_admitted = sum(1 for entry in macro_ledger if entry.get("event") == "ADMIT")
    macro_activated = sum(1 for entry in macro_ledger if entry.get("event") == "ACTIVATE")
    macro_evicted = sum(1 for entry in macro_ledger if entry.get("event") == "EVICT")

    metabolism_admitted = sum(1 for entry in metabolism_ledger if entry.get("event") == "ADMIT")
    metabolism_activated = sum(1 for entry in metabolism_ledger if entry.get("event") == "ACTIVATE")
    metabolism_evicted = sum(1 for entry in metabolism_ledger if entry.get("event") == "EVICT")

    active_onto_path = ontology_root / "active" / "ontology_active_set_v3.json"
    active_macro_path = macro_root / "active" / "macro_active_set_v2.json"
    active_patch_path = metabolism_root / "active" / "meta_patch_active_set_v1.json"

    active_onto = load_canon_json(active_onto_path) if active_onto_path.exists() else {}
    active_macro = load_canon_json(active_macro_path) if active_macro_path.exists() else {}
    active_patch = load_canon_json(active_patch_path) if active_patch_path.exists() else {}

    active_macro_ids = active_macro.get("active_macro_ids") if isinstance(active_macro, dict) else []
    if not isinstance(active_macro_ids, list):
        active_macro_ids = []

    active_patch_ids = active_patch.get("active_patch_ids") if isinstance(active_patch, dict) else []
    if not isinstance(active_patch_ids, list):
        active_patch_ids = []

    latest_onto_report = _latest_report(ontology_root / "reports", "ontology_eval_report_v3")
    latest_macro_report = _latest_report(macro_root / "reports", "macro_eval_report_v2")

    latest_dl_gain = int(latest_onto_report.get("dl", {}).get("dl_gain_bits", 0))
    latest_support = int(latest_onto_report.get("dl", {}).get("support_families_improved", 0))
    latest_corpus_hash = latest_onto_report.get("corpus", {}).get("corpus_hash")

    best_macro = latest_macro_report.get("best_macro", {}) if isinstance(latest_macro_report, dict) else {}
    best_ctx_mdl_gain = int(best_macro.get("ctx_mdl_gain_bits", 0))
    best_support = int(best_macro.get("support_families_hold", 0))

    activation_epoch = active_patch.get("activation_epoch") if isinstance(active_patch, dict) else None
    latest_eval_epoch = f"epoch_{activation_epoch}" if isinstance(activation_epoch, int) else None
    metabolism_report = None
    workvec_base = {
        "schema": "workvec_v1",
        "schema_version": 1,
        "sha256_calls_total": 0,
        "canon_calls_total": 0,
        "sha256_bytes_total": 0,
        "canon_bytes_total": 0,
        "onto_ctx_hash_compute_calls_total": 0,
    }
    workvec_patch = dict(workvec_base)
    if isinstance(activation_epoch, int):
        report_path = metabolism_root / "reports" / f"meta_patch_eval_report_v1_epoch_{activation_epoch}.json"
        if report_path.exists():
            metabolism_report = load_canon_json(report_path)
            workvec_base = metabolism_report.get("workvec_base", workvec_base)
            workvec_patch = metabolism_report.get("workvec_patch", workvec_patch)

    verdict = "VALID"
    if ontology_admitted < 1 or ontology_activated < 1:
        verdict = "INVALID"
    if macro_admitted < 1 or macro_activated < 1:
        verdict = "INVALID"
    if metabolism_admitted < 1 or metabolism_activated < 1:
        verdict = "INVALID"
    if latest_dl_gain < int(constants.get("ONTO_V3_DL_GAIN_MIN_BITS", 0) or 0):
        verdict = "INVALID"
    if latest_support < int(constants.get("ONTO_V3_SUPPORT_FAMILIES_MIN", 0) or 0):
        verdict = "INVALID"
    if best_ctx_mdl_gain < int(constants.get("MACRO_V2_CTX_MDL_GAIN_MIN_BITS", 0) or 0):
        verdict = "INVALID"
    if best_support < int(constants.get("MACRO_V2_SUPPORT_FAMILIES_MIN", 0) or 0):
        verdict = "INVALID"
    if not active_onto.get("active_ontology_id") or not active_onto.get("active_snapshot_id"):
        verdict = "INVALID"
    if len(active_macro_ids) < 1:
        verdict = "INVALID"
    if len(active_patch_ids) != 1:
        verdict = "INVALID"
    if metabolism_report is not None:
        decision = metabolism_report.get("decision", {}) if isinstance(metabolism_report, dict) else {}
        if not bool(decision.get("passes")):
            verdict = "INVALID"
    else:
        verdict = "INVALID"

    return {
        "schema": "rsi_demon_receipt_v4",
        "schema_version": 4,
        "final_epoch": f"epoch_{final_epoch}",
        "verdict": verdict,
        "ontology_v3": {
            "admitted": ontology_admitted,
            "activated": ontology_activated,
            "evicted": ontology_evicted,
            "active_ontology_id": active_onto.get("active_ontology_id"),
            "active_snapshot_id": active_onto.get("active_snapshot_id"),
            "latest_dl_gain_bits": latest_dl_gain,
            "latest_support_families_improved": latest_support,
            "latest_corpus_hash": latest_corpus_hash,
        },
        "macros_v2": {
            "admitted": macro_admitted,
            "activated": macro_activated,
            "evicted": macro_evicted,
            "active_macro_count": len(active_macro_ids),
            "best_ctx_mdl_gain_bits": best_ctx_mdl_gain,
            "best_support_families_hold": best_support,
        },
        "metabolism_v1": {
            "admitted": metabolism_admitted,
            "activated": metabolism_activated,
            "evicted": metabolism_evicted,
            "active_patch_ids": active_patch_ids,
            "latest_eval_epoch": latest_eval_epoch,
            "workvec_base": workvec_base,
            "workvec_patch": workvec_patch,
        },
        "x-meta": meta,
    }


def write_receipt(*, state_dir: Path, run_id: str, final_epoch: int) -> Path:
    receipt = build_receipt(state_dir=state_dir, run_id=run_id, final_epoch=final_epoch)
    out_path = state_dir / "epochs" / f"epoch_{final_epoch}" / "diagnostics" / "rsi_demon_receipt_v4.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)
    return out_path
