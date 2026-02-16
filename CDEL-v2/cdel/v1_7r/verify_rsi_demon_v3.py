"""Verifier for RSI demon v3 runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed
from .constants import meta_identities, require_constants
from .ontology_v3.io import ensure_ontology_dirs, load_def_by_ontology_id, load_snapshot_by_id
from .ontology_v3.ledger import load_ledger_entries as load_ontology_ledger
from .macros_v2.io import ensure_macro_dirs
from .macros_v2.ledger import load_ledger_entries as load_macro_ledger


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _verify_xmeta(payload: dict[str, Any], meta: dict[str, str]) -> None:
    xmeta = payload.get("x-meta")
    if not isinstance(xmeta, dict):
        _fail("x-meta missing")
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash"):
        if xmeta.get(key) != meta.get(key):
            _fail("x-meta mismatch")


def _latest_report(dir_path: Path, prefix: str) -> dict[str, Any]:
    if not dir_path.exists():
        _fail("missing reports dir")
    best_epoch = None
    best_path = None
    for report_path in dir_path.glob(f"{prefix}_epoch_*.json"):
        tail = report_path.stem.split("_epoch_")[-1]
        if not tail.isdigit():
            continue
        idx = int(tail)
        if best_epoch is None or idx > best_epoch:
            best_epoch = idx
            best_path = report_path
    if best_path is None:
        _fail("missing report")
    return load_canon_json(best_path)


def _trace_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _corpus_hash(window_epochs: list[int], trace_hashes: list[str]) -> str:
    payload = {"window_epochs": window_epochs, "trace_hashes": trace_hashes}
    return sha256_prefixed(canon_bytes(payload))


def _verify_ontology(state_dir: Path, constants: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    ontology_root = state_dir / "current" / "ontology_v3"
    dirs = ensure_ontology_dirs(ontology_root)
    ledger_path = dirs["ledger"] / "ontology_ledger_v3.jsonl"
    ledger = load_ontology_ledger(ledger_path)
    if not ledger:
        _fail("ontology ledger empty")
    for entry in ledger:
        if entry.get("schema") != "ontology_ledger_entry_v3":
            _fail("ontology ledger schema mismatch")
        if int(entry.get("schema_version", 0)) != 3:
            _fail("ontology ledger schema_version mismatch")
        _verify_xmeta(entry, meta)

    active_path = dirs["active"] / "ontology_active_set_v3.json"
    if not active_path.exists():
        _fail("missing ontology active set")
    active = load_canon_json(active_path)
    if active.get("schema") != "ontology_active_set_v3":
        _fail("ontology active set schema mismatch")
    _verify_xmeta(active, meta)
    active_ontology_id = active.get("active_ontology_id")
    active_snapshot_id = active.get("active_snapshot_id")
    if not isinstance(active_ontology_id, str) or not isinstance(active_snapshot_id, str):
        _fail("ontology active set missing ids")

    load_def_by_ontology_id(active_ontology_id, defs_root=dirs["defs"])
    load_snapshot_by_id(active_snapshot_id, snapshots_root=dirs["snapshots"])

    report = _latest_report(dirs["reports"], "ontology_eval_report_v3")
    if report.get("schema") != "ontology_eval_report_v3":
        _fail("ontology report schema mismatch")
    if int(report.get("schema_version", 0)) != 3:
        _fail("ontology report schema_version mismatch")
    _verify_xmeta(report, meta)
    if report.get("ontology_id") != active_ontology_id:
        _fail("ontology report ontology_id mismatch")
    if report.get("snapshot_id") != active_snapshot_id:
        _fail("ontology report snapshot_id mismatch")

    dl = report.get("dl", {}) if isinstance(report.get("dl"), dict) else {}
    if int(dl.get("dl_gain_bits", 0)) < int(constants.get("ONTO_V3_DL_GAIN_MIN_BITS", 0) or 0):
        _fail("ontology dl_gain_bits below minimum")
    if int(dl.get("support_families_improved", 0)) < int(constants.get("ONTO_V3_SUPPORT_FAMILIES_MIN", 0) or 0):
        _fail("ontology support_families_improved below minimum")

    corpus = report.get("corpus", {}) if isinstance(report.get("corpus"), dict) else {}
    window_epochs = corpus.get("window_epochs")
    trace_hashes = corpus.get("trace_hashes")
    if not isinstance(window_epochs, list) or not isinstance(trace_hashes, list):
        _fail("ontology corpus window invalid")
    for idx in window_epochs:
        trace_path = state_dir / "epochs" / f"epoch_{idx}" / "traces" / "trace_v2.jsonl"
        if not trace_path.exists():
            _fail("missing trace_v2.jsonl")
    computed_hashes = [_trace_hash(state_dir / "epochs" / f"epoch_{idx}" / "traces" / "trace_v2.jsonl") for idx in window_epochs]
    if computed_hashes != trace_hashes:
        _fail("ontology trace_hashes mismatch")
    if corpus.get("corpus_hash") != _corpus_hash(window_epochs, trace_hashes):
        _fail("ontology corpus_hash mismatch")

    return report


def _verify_macros(state_dir: Path, constants: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    macros_root = state_dir / "current" / "macros_v2"
    dirs = ensure_macro_dirs(macros_root)
    ledger_path = dirs["ledger"] / "macro_ledger_v2.jsonl"
    ledger = load_macro_ledger(ledger_path)
    if not ledger:
        _fail("macro ledger empty")
    for entry in ledger:
        if entry.get("schema") != "macro_ledger_entry_v2":
            _fail("macro ledger schema mismatch")
        if int(entry.get("schema_version", 0)) != 2:
            _fail("macro ledger schema_version mismatch")
        _verify_xmeta(entry, meta)

    active_path = dirs["active"] / "macro_active_set_v2.json"
    if not active_path.exists():
        _fail("missing macro active set")
    active = load_canon_json(active_path)
    if active.get("schema") != "macro_active_set_v2":
        _fail("macro active set schema mismatch")
    _verify_xmeta(active, meta)
    active_ids = active.get("active_macro_ids")
    if not isinstance(active_ids, list) or len(active_ids) < 1:
        _fail("macro active set empty")

    report = _latest_report(dirs["reports"], "macro_eval_report_v2")
    if report.get("schema") != "macro_eval_report_v2":
        _fail("macro report schema mismatch")
    if int(report.get("schema_version", 0)) != 2:
        _fail("macro report schema_version mismatch")
    _verify_xmeta(report, meta)

    best_macro = report.get("best_macro", {}) if isinstance(report.get("best_macro"), dict) else {}
    if int(best_macro.get("ctx_mdl_gain_bits", 0)) < int(constants.get("MACRO_V2_CTX_MDL_GAIN_MIN_BITS", 0) or 0):
        _fail("macro ctx_mdl_gain_bits below minimum")
    if int(best_macro.get("support_families_hold", 0)) < int(constants.get("MACRO_V2_SUPPORT_FAMILIES_MIN", 0) or 0):
        _fail("macro support_families_hold below minimum")

    corpus = report.get("corpus", {}) if isinstance(report.get("corpus"), dict) else {}
    window_epochs = corpus.get("window_epochs")
    trace_hashes = corpus.get("trace_hashes")
    if not isinstance(window_epochs, list) or not isinstance(trace_hashes, list):
        _fail("macro corpus window invalid")
    for idx in window_epochs:
        trace_path = state_dir / "epochs" / f"epoch_{idx}" / "traces" / "trace_v2.jsonl"
        if not trace_path.exists():
            _fail("missing trace_v2.jsonl")
    computed_hashes = [_trace_hash(state_dir / "epochs" / f"epoch_{idx}" / "traces" / "trace_v2.jsonl") for idx in window_epochs]
    if computed_hashes != trace_hashes:
        _fail("macro trace_hashes mismatch")
    if corpus.get("corpus_hash") != _corpus_hash(window_epochs, trace_hashes):
        _fail("macro corpus_hash mismatch")

    return report


def _verify_receipt(state_dir: Path, meta: dict[str, str]) -> None:
    epochs_dir = state_dir / "epochs"
    if not epochs_dir.exists():
        _fail("missing epochs dir")
    latest_epoch = None
    latest_path = None
    for epoch_dir in epochs_dir.glob("epoch_*"):
        tail = epoch_dir.name.split("_")[-1]
        if not tail.isdigit():
            continue
        idx = int(tail)
        receipt_path = epoch_dir / "diagnostics" / "rsi_demon_receipt_v3.json"
        if receipt_path.exists() and (latest_epoch is None or idx > latest_epoch):
            latest_epoch = idx
            latest_path = receipt_path
    if latest_path is None:
        _fail("missing rsi_demon_receipt_v3.json")
    receipt = load_canon_json(latest_path)
    if receipt.get("schema") != "rsi_demon_receipt_v3":
        _fail("receipt schema mismatch")
    if int(receipt.get("schema_version", 0)) != 3:
        _fail("receipt schema_version mismatch")
    _verify_xmeta(receipt, meta)
    if receipt.get("verdict") != "VALID":
        _fail("receipt verdict invalid")


def verify(state_dir: Path) -> None:
    constants = require_constants()
    meta = meta_identities()
    _verify_ontology(state_dir, constants, meta)
    _verify_macros(state_dir, constants, meta)
    _verify_receipt(state_dir, meta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI demon v3 run")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.state_dir))
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        print(f"INVALID: {reason}")
        return
    print("VALID")


if __name__ == "__main__":
    main()
