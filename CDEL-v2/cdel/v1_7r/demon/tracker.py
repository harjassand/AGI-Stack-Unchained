"""Final receipt tracker for RSI demon v3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, load_canon_json, write_canon_json
from ..constants import meta_identities, require_constants
from ..ontology_v3.ledger import load_ledger_entries as load_ontology_ledger
from ..macros_v2.ledger import load_ledger_entries as load_macro_ledger


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

    ontology_ledger = load_ontology_ledger(ontology_root / "ledger" / "ontology_ledger_v3.jsonl")
    macro_ledger = load_macro_ledger(macro_root / "ledger" / "macro_ledger_v2.jsonl")

    ontology_admitted = sum(1 for entry in ontology_ledger if entry.get("event") == "ADMIT")
    ontology_activated = sum(1 for entry in ontology_ledger if entry.get("event") == "ACTIVATE")
    macro_admitted = sum(1 for entry in macro_ledger if entry.get("event") == "ADMIT")
    macro_activated = sum(1 for entry in macro_ledger if entry.get("event") == "ACTIVATE")

    active_onto_path = ontology_root / "active" / "ontology_active_set_v3.json"
    active_macro_path = macro_root / "active" / "macro_active_set_v2.json"

    active_onto = load_canon_json(active_onto_path) if active_onto_path.exists() else {}
    active_macro = load_canon_json(active_macro_path) if active_macro_path.exists() else {}

    latest_onto_report = _latest_report(ontology_root / "reports", "ontology_eval_report_v3")
    latest_macro_report = _latest_report(macro_root / "reports", "macro_eval_report_v2")

    latest_dl_gain = int(latest_onto_report.get("dl", {}).get("dl_gain_bits", 0))
    latest_support = int(latest_onto_report.get("dl", {}).get("support_families_improved", 0))
    latest_corpus_hash = latest_onto_report.get("corpus", {}).get("corpus_hash")

    best_macro = latest_macro_report.get("best_macro", {}) if isinstance(latest_macro_report, dict) else {}
    best_ctx_mdl_gain = int(best_macro.get("ctx_mdl_gain_bits", 0))
    best_support = int(best_macro.get("support_families_hold", 0))

    active_macro_ids = active_macro.get("active_macro_ids") if isinstance(active_macro, dict) else []
    if not isinstance(active_macro_ids, list):
        active_macro_ids = []

    verdict = "VALID"
    if ontology_admitted < 1 or ontology_activated < 1:
        verdict = "INVALID"
    if macro_admitted < 1 or macro_activated < 1:
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

    return {
        "schema": "rsi_demon_receipt_v3",
        "schema_version": 3,
        "run_id": run_id,
        "final_epoch": f"epoch_{final_epoch}",
        "ontology_v3": {
            "admitted": ontology_admitted,
            "activated": ontology_activated,
            "active_ontology_id": active_onto.get("active_ontology_id"),
            "active_snapshot_id": active_onto.get("active_snapshot_id"),
            "latest_dl_gain_bits": latest_dl_gain,
            "latest_support_families_improved": latest_support,
            "latest_corpus_hash": latest_corpus_hash,
        },
        "macros_v2": {
            "admitted": macro_admitted,
            "activated": macro_activated,
            "active_macro_count": len(active_macro_ids),
            "best_ctx_mdl_gain_bits": best_ctx_mdl_gain,
            "best_support_families_hold": best_support,
        },
        "verdict": verdict,
        "x-meta": meta,
    }


def write_receipt(*, state_dir: Path, run_id: str, final_epoch: int) -> Path:
    receipt = build_receipt(state_dir=state_dir, run_id=run_id, final_epoch=final_epoch)
    out_path = state_dir / "epochs" / f"epoch_{final_epoch}" / "diagnostics" / "rsi_demon_receipt_v3.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)
    return out_path
