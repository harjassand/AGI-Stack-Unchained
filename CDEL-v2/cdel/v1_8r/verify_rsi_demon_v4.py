"""Verifier for RSI demon v4 runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed
from ..v1_7r.constants import meta_identities as meta_identities_v1_7r
from ..v1_7r.constants import require_constants as require_constants_v1_7r
from ..v1_7r.ontology_v3.io import ensure_ontology_dirs, load_def_by_ontology_id, load_snapshot_by_id
from ..v1_7r.ontology_v3.ledger import load_ledger_entries as load_ontology_ledger
from ..v1_7r.macros_v2.io import ensure_macro_dirs
from ..v1_7r.macros_v2.ledger import load_ledger_entries as load_macro_ledger
from .constants import meta_identities, require_constants
from .demon.tracker import build_receipt
from .metabolism_v1.io import compute_patch_id, ensure_metabolism_dirs, load_patch_def
from .metabolism_v1.ledger import load_ledger_entries as load_metabolism_ledger
from .metabolism_v1.translation import evaluate_translation, load_translation_inputs, translation_inputs_hash


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def _verify_metabolism(state_dir: Path, constants: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    metabolism_root = state_dir / "current" / "metabolism_v1"
    dirs = ensure_metabolism_dirs(metabolism_root)
    ledger_path = dirs["ledger"] / "meta_patch_ledger_v1.jsonl"
    ledger = load_metabolism_ledger(ledger_path)
    if not ledger:
        _fail("metabolism ledger empty")
    for entry in ledger:
        if entry.get("schema") != "meta_patch_ledger_entry_v1":
            _fail("meta patch ledger schema mismatch")
        if int(entry.get("schema_version", 0)) != 1:
            _fail("meta patch ledger schema_version mismatch")
        _verify_xmeta(entry, meta)
        event = entry.get("event")
        if event == "ADMIT":
            if entry.get("patch_def_hash") is None or entry.get("meta_patch_admit_receipt_hash") is None:
                _fail("meta patch admit entry missing hashes")
        elif event in {"ACTIVATE", "DEACTIVATE", "EVICT"}:
            if entry.get("patch_def_hash") is not None or entry.get("meta_patch_admit_receipt_hash") is not None:
                _fail("meta patch non-admit entry should not include hashes")
        else:
            _fail("meta patch ledger event invalid")

    active_path = dirs["active"] / "meta_patch_active_set_v1.json"
    if not active_path.exists():
        _fail("missing meta patch active set")
    active = load_canon_json(active_path)
    if active.get("schema") != "meta_patch_active_set_v1":
        _fail("meta patch active set schema mismatch")
    if int(active.get("schema_version", 0)) != 1:
        _fail("meta patch active set schema_version mismatch")
    _verify_xmeta(active, meta)
    active_ids = active.get("active_patch_ids")
    if not isinstance(active_ids, list) or len(active_ids) != 1:
        _fail("meta patch active set must contain exactly one patch id")
    sorted_ids = sorted({str(x) for x in active_ids if isinstance(x, str)})
    if active_ids != sorted_ids:
        _fail("meta patch active ids not sorted")
    patch_id = active_ids[0]

    activation_epoch = active.get("activation_epoch")
    if not isinstance(activation_epoch, int):
        _fail("meta patch activation_epoch missing")
    epoch_id = f"epoch_{activation_epoch}"

    patch_def = load_patch_def(patch_id, defs_root=dirs["defs"])
    if patch_def.get("schema") != "meta_patch_def_v1":
        _fail("meta patch def schema mismatch")
    if int(patch_def.get("schema_version", 0)) != 1:
        _fail("meta patch def schema_version mismatch")
    _verify_xmeta(patch_def, meta)
    if patch_def.get("patch_id") != compute_patch_id(patch_def):
        _fail("meta patch def patch_id mismatch")
    if patch_def.get("patch_kind") != "ctx_hash_cache_v1":
        _fail("meta patch def kind invalid")
    params = patch_def.get("params") if isinstance(patch_def.get("params"), dict) else {}
    capacity = int(params.get("capacity", 0))
    max_capacity = int(constants.get("CTX_HASH_CACHE_V1_MAX_CAPACITY", 0) or 0)
    if capacity < 1 or capacity > max_capacity:
        _fail("meta patch capacity out of range")

    report_path = dirs["reports"] / f"meta_patch_eval_report_v1_epoch_{activation_epoch}.json"
    if not report_path.exists():
        _fail("missing meta patch eval report")
    report = load_canon_json(report_path)
    if report.get("schema") != "meta_patch_eval_report_v1":
        _fail("meta patch report schema mismatch")
    if int(report.get("schema_version", 0)) != 1:
        _fail("meta patch report schema_version mismatch")
    _verify_xmeta(report, meta)
    if report.get("epoch_id") != epoch_id:
        _fail("meta patch report epoch mismatch")
    if report.get("patch_id") != patch_id:
        _fail("meta patch report patch_id mismatch")
    if report.get("patch_def_hash") != hash_json(patch_def):
        _fail("meta patch report patch_def_hash mismatch")

    translation_path = _repo_root() / "campaigns" / "rsi_real_demon_v4" / "translation" / "translation_inputs_v1.json"
    translation_inputs = load_translation_inputs(translation_path)
    if report.get("translation_inputs_hash") != translation_inputs_hash(translation_inputs):
        _fail("translation_inputs_hash mismatch")

    eval_result = evaluate_translation(
        translation_inputs=translation_inputs,
        cache_capacity=capacity,
        min_sha256_delta=int(constants.get("METAPATCH_V1_MIN_SHA256_CALL_DELTA", 0) or 0),
    )

    expected_results = eval_result.get("translation_results", [])
    if report.get("translation_results") != expected_results:
        _fail("translation_results mismatch")

    workvec_base = eval_result.get("workvec_base")
    workvec_patch = eval_result.get("workvec_patch")
    if report.get("workvec_base") != workvec_base.to_dict():
        _fail("workvec_base mismatch")
    if report.get("workvec_patch") != workvec_patch.to_dict():
        _fail("workvec_patch mismatch")

    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    expected_passes = bool(eval_result.get("decision", {}).get("passes"))
    if bool(decision.get("passes")) != expected_passes:
        _fail("meta patch decision mismatch")

    receipt_path = dirs["receipts"] / f"meta_patch_admit_receipt_v1_epoch_{activation_epoch}.json"
    if not receipt_path.exists():
        _fail("missing meta patch admit receipt")
    receipt = load_canon_json(receipt_path)
    if receipt.get("schema") != "meta_patch_admit_receipt_v1":
        _fail("meta patch receipt schema mismatch")
    if int(receipt.get("schema_version", 0)) != 1:
        _fail("meta patch receipt schema_version mismatch")
    _verify_xmeta(receipt, meta)
    if receipt.get("epoch_id") != epoch_id:
        _fail("meta patch receipt epoch mismatch")
    if receipt.get("patch_id") != patch_id:
        _fail("meta patch receipt patch_id mismatch")
    if receipt.get("patch_def_hash") != hash_json(patch_def):
        _fail("meta patch receipt patch_def_hash mismatch")
    if receipt.get("meta_patch_eval_report_hash") != hash_json(report):
        _fail("meta patch receipt report hash mismatch")
    if receipt.get("verdict") != "VALID":
        _fail("meta patch receipt verdict invalid")

    admit_ok = any(e.get("event") == "ADMIT" and e.get("epoch_id") == epoch_id and e.get("patch_id") == patch_id for e in ledger)
    activate_ok = any(
        e.get("event") == "ACTIVATE" and e.get("epoch_id") == epoch_id and e.get("patch_id") == patch_id for e in ledger
    )
    if not admit_ok or not activate_ok:
        _fail("meta patch ledger missing admit/activate in activation epoch")

    return report


def _verify_receipt(state_dir: Path, meta: dict[str, str]) -> None:
    receipt_path = state_dir / "epochs" / "epoch_6" / "diagnostics" / "rsi_demon_receipt_v4.json"
    if not receipt_path.exists():
        _fail("missing rsi_demon_receipt_v4.json")
    receipt = load_canon_json(receipt_path)
    if receipt.get("schema") != "rsi_demon_receipt_v4":
        _fail("receipt schema mismatch")
    if int(receipt.get("schema_version", 0)) != 4:
        _fail("receipt schema_version mismatch")
    _verify_xmeta(receipt, meta)
    expected = build_receipt(state_dir=state_dir, run_id="", final_epoch=6)
    if receipt != expected:
        _fail("receipt contents mismatch")
    if receipt.get("verdict") != "VALID":
        _fail("receipt verdict invalid")


def verify(state_dir: Path) -> None:
    constants_onto = require_constants_v1_7r()
    meta_onto = meta_identities_v1_7r()
    constants_meta = require_constants()
    meta_meta = meta_identities()
    _verify_ontology(state_dir, constants_onto, meta_onto)
    _verify_macros(state_dir, constants_onto, meta_onto)
    _verify_metabolism(state_dir, constants_meta, meta_meta)
    _verify_receipt(state_dir, meta_meta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI demon v4 run")
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
