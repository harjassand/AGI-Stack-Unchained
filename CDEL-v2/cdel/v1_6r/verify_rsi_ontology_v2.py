"""Replay verifier for RSI ontology v2 artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .canon import CanonError, hash_json, load_canon_json
from .constants import meta_identities, require_constants
from .ontology_v2.dl_metric import compute_dl_metrics, corpus_hash
from .ontology_v2.dsl import validate_ontology_def
from .ontology_v2.io import load_def_by_hash
from .ontology_v2.ledger import load_ledger_entries
from .ctime.trace import load_trace_jsonl


def _epoch_index(epoch_id: str) -> int | None:
    tail = str(epoch_id).split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _trace_path(state_dir: Path, epoch_idx: int) -> Path:
    epoch_dir = state_dir / "epochs" / f"epoch_{epoch_idx}" / "traces"
    trace_v1 = epoch_dir / "trace_v1.jsonl"
    if trace_v1.exists():
        return trace_v1
    return epoch_dir / "trace_heldout_v1.jsonl"


def _hash_file(path: Path) -> str:
    from .canon import sha256_prefixed

    return sha256_prefixed(path.read_bytes())


def _meta_ok(xmeta: dict[str, Any], meta: dict[str, str]) -> bool:
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash", "toolchain_root"):
        if xmeta.get(key) != meta.get(key):
            return False
    return True


def _load_corpus(state_dir: Path, window_epochs: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    trace_hashes: list[str] = []
    for idx in window_epochs:
        trace_path = _trace_path(state_dir, idx)
        if not trace_path.exists():
            raise CanonError(f"missing trace: {trace_path}")
        trace_hashes.append(_hash_file(trace_path))
        events.extend(load_trace_jsonl(trace_path))
    return events, trace_hashes


def _latest_eval_report(reports_dir: Path) -> dict[str, Any] | None:
    latest_report = None
    latest_idx = None
    for path in sorted(reports_dir.glob("ontology_eval_report_v2_*.json")):
        report = load_canon_json(path)
        epoch_id = report.get("epoch_id")
        if not isinstance(epoch_id, str):
            continue
        idx = _epoch_index(epoch_id)
        if idx is None:
            continue
        if latest_idx is None or idx > latest_idx:
            latest_idx = idx
            latest_report = report
    return latest_report


def verify(state_dir: Path) -> tuple[bool, str]:
    constants = require_constants()
    meta = meta_identities()

    ontology_root = state_dir / "current" / "ontology"
    ledger_path = ontology_root / "ontology_ledger_v2.jsonl"
    if not ledger_path.exists():
        return False, "missing ontology_ledger_v2.jsonl"

    try:
        entries = load_ledger_entries(ledger_path)
    except Exception as exc:
        return False, f"ledger error: {exc}"

    admitted_ids: set[str] = set()
    admit_receipt_hashes: set[str] = set()
    admit_count = 0
    activate_count = 0
    for entry in entries:
        if entry.get("schema") != "ontology_ledger_entry_v2":
            return False, "ledger schema mismatch"
        if int(entry.get("schema_version", 0)) != 2:
            return False, "ledger schema_version mismatch"
        xmeta = entry.get("x-meta")
        if not isinstance(xmeta, dict) or not _meta_ok(xmeta, meta):
            return False, "ledger x-meta mismatch"
        event = entry.get("event")
        ontology_id = entry.get("ontology_id")
        if event == "ADMIT":
            admit_count += 1
            def_hash = entry.get("ontology_def_hash")
            receipt_hash = entry.get("admit_receipt_hash")
            if not isinstance(def_hash, str) or not isinstance(receipt_hash, str):
                return False, "ADMIT missing hashes"
            def_path = ontology_root / "defs" / f"{def_hash.split(':',1)[1]}.json"
            if not def_path.exists():
                return False, "missing ontology_def for ADMIT"
            ontology_def = load_canon_json(def_path)
            if hash_json(ontology_def) != def_hash:
                return False, "ontology_def hash mismatch"
            validate_ontology_def(ontology_def, constants=constants)
            receipt_path = ontology_root / "receipts" / f"ontology_admit_receipt_v2_{entry.get('epoch_id')}.json"
            if not receipt_path.exists():
                return False, "missing ontology_admit_receipt"
            receipt = load_canon_json(receipt_path)
            if hash_json(receipt) != receipt_hash:
                return False, "ontology_admit_receipt hash mismatch"
            if receipt.get("verdict") != "VALID":
                return False, "ontology_admit_receipt verdict invalid"
            if receipt.get("ontology_id") != ontology_id:
                return False, "ontology_admit_receipt ontology_id mismatch"
            if receipt.get("ontology_def_hash") != def_hash:
                return False, "ontology_admit_receipt def hash mismatch"
            admit_receipt_hashes.add(receipt_hash)
            if isinstance(ontology_id, str):
                admitted_ids.add(ontology_id)

            report_hash = receipt.get("ontology_eval_report_hash")
            if not isinstance(report_hash, str):
                return False, "missing ontology_eval_report_hash"
            report_path = ontology_root / "reports" / f"ontology_eval_report_v2_{entry.get('epoch_id')}.json"
            if not report_path.exists():
                return False, "missing ontology_eval_report"
            report = load_canon_json(report_path)
            if hash_json(report) != report_hash:
                return False, "ontology_eval_report hash mismatch"
            # recompute DL metrics
            window_epochs = report.get("corpus", {}).get("window_epochs", [])
            if not isinstance(window_epochs, list) or not all(isinstance(x, int) for x in window_epochs):
                return False, "ontology_eval_report window_epochs invalid"
            events, trace_hashes = _load_corpus(state_dir, window_epochs)
            if trace_hashes != report.get("corpus", {}).get("trace_hashes"):
                return False, "ontology_eval_report trace_hashes mismatch"
            if corpus_hash(window_epochs, trace_hashes) != report.get("corpus", {}).get("corpus_hash"):
                return False, "ontology_eval_report corpus_hash mismatch"
            base_id = report.get("base_ontology_id")
            base_def = None
            if isinstance(base_id, str):
                base_def = load_def_by_hash(base_id, inbox_root=state_dir / "current" / "inbox" / "ontology_v2", defs_root=ontology_root / "defs")
                validate_ontology_def(base_def, constants=constants)
            new_metrics = compute_dl_metrics(events=events, ontology_def=ontology_def)
            base_metrics = compute_dl_metrics(events=events, ontology_def=base_def)
            dl_block = report.get("dl", {}) if isinstance(report.get("dl"), dict) else {}
            if int(dl_block.get("dl_bits_new", -1)) != new_metrics.dl_bits:
                return False, "ontology_eval_report dl_bits_new mismatch"
            if int(dl_block.get("dl_bits_base", -1)) != base_metrics.dl_bits:
                return False, "ontology_eval_report dl_bits_base mismatch"
        elif event == "ACTIVATE":
            activate_count += 1
            if not isinstance(ontology_id, str) or ontology_id not in admitted_ids:
                return False, "ACTIVATE without prior ADMIT"
            snap_hash = entry.get("active_snapshot_hash")
            if isinstance(snap_hash, str):
                snap_path = ontology_root / "snapshots" / f"{snap_hash.split(':',1)[1]}.json"
                if not snap_path.exists():
                    return False, "missing active_snapshot for ACTIVATE"
                if hash_json(load_canon_json(snap_path)) != snap_hash:
                    return False, "active_snapshot hash mismatch"
        elif event == "EVICT":
            if not isinstance(ontology_id, str) or ontology_id not in admitted_ids:
                return False, "EVICT without prior ADMIT"

    if admit_count < 1 or activate_count < 1:
        return False, "missing ADMIT/ACTIVATE"

    receipt_path = state_dir / "epochs" / state_dir.name / "diagnostics" / "rsi_ontology_receipt_v2.json"
    if not receipt_path.exists():
        # fallback: use last epoch folder
        epoch_dirs = sorted((state_dir / "epochs").glob("epoch_*"))
        if epoch_dirs:
            receipt_path = epoch_dirs[-1] / "diagnostics" / "rsi_ontology_receipt_v2.json"
    if not receipt_path.exists():
        return False, "missing rsi_ontology_receipt_v2"
    receipt = load_canon_json(receipt_path)
    if receipt.get("verdict") != "VALID":
        return False, "rsi_ontology_receipt_v2 verdict invalid"

    latest_report = _latest_eval_report(ontology_root / "reports")
    if not isinstance(latest_report, dict):
        return False, "missing ontology_eval_report_v2"
    dl_block = latest_report.get("dl") if isinstance(latest_report.get("dl"), dict) else {}
    min_gain = int(constants.get("ontology", {}).get("ONTO_DL_GAIN_MIN_BITS", 0) or 0)
    min_support = int(constants.get("ontology", {}).get("ONTO_SUPPORT_FAMILIES_MIN", 0) or 0)
    if int(dl_block.get("dl_gain_bits", -1)) < min_gain:
        return False, "dl_gain_bits below minimum"
    if int(dl_block.get("support_families_improved", -1)) < min_support:
        return False, "support_families_improved below minimum"

    return True, "VALID"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    ok, reason = verify(Path(args.state_dir))
    if ok:
        print("VALID")
    else:
        print(f"INVALID: {reason}")


if __name__ == "__main__":
    main()
