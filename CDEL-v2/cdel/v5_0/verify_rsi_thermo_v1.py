"""Verifier for RSI Thermodynamic Integration v5.0 (thermo protocol v1)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed
from ..v2_3.immutable_core import load_lock, validate_lock
from .constants import meta_identities, require_constants
from .thermo_ledger import load_thermo_ledger, validate_thermo_chain
from .thermo_metrics import ProbeResult, trailing_consecutive_meeting_threshold
from .thermo_verify_utils import (
    compute_pack_hash,
    compute_receipt_hash,
    load_required_canon_json,
    resolve_pack_path,
    sha256_file_hex,
    sha256_file_prefixed,
)


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root_from_state_dir(state_dir: Path) -> Path:
    # state_dir is <repo>/runs/<run_name>
    return state_dir.parent.parent


def _find_pack(state_dir: Path) -> tuple[Path, dict[str, Any]]:
    preferred = state_dir / "rsi_real_thermo_pack_v1.json"
    if preferred.exists():
        return preferred, load_required_canon_json(preferred)
    for path in state_dir.glob("*.json"):
        try:
            payload = load_required_canon_json(path)
        except Exception:
            continue
        if payload.get("pack_version") == "rsi_real_thermo_pack_v1":
            return path, payload
    _fail("MISSING_ARTIFACT")
    raise AssertionError


def _load_toolchain_manifest(state_dir: Path, ledger_events: list[dict[str, Any]]) -> tuple[Path, str]:
    for ev in ledger_events:
        if ev.get("event_type") == "THERMO_ENV_SNAPSHOT":
            payload = ev.get("payload") or {}
            p = payload.get("toolchain_manifest_path")
            h = payload.get("toolchain_manifest_hash")
            if not isinstance(p, str) or not isinstance(h, str):
                _fail("SCHEMA_INVALID")
            repo_root = _repo_root_from_state_dir(state_dir)
            manifest_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=p)
            if not manifest_path.exists():
                _fail("MISSING_ARTIFACT")
            manifest = load_required_canon_json(manifest_path)
            if sha256_prefixed(canon_bytes(manifest)) != h:
                _fail("CANON_HASH_MISMATCH")
            return manifest_path, h
    _fail("MISSING_ARTIFACT")
    raise AssertionError


def _collect_probe_receipts(state_dir: Path, repo_root: Path, ledger_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for ev in ledger_events:
        if ev.get("event_type") != "THERMO_PROBE_END":
            continue
        payload = ev.get("payload") or {}
        receipt_path_s = payload.get("probe_receipt_path")
        receipt_hash = payload.get("probe_receipt_hash")
        if not isinstance(receipt_path_s, str) or not isinstance(receipt_hash, str):
            _fail("SCHEMA_INVALID")
        receipt_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=receipt_path_s)
        receipt = load_required_canon_json(receipt_path)
        if receipt.get("schema") != "thermo_probe_receipt_v1" or receipt.get("spec_version") != "v5_0":
            _fail("SCHEMA_INVALID")
        expected_receipt_hash = compute_receipt_hash(receipt)
        if receipt.get("receipt_hash") != expected_receipt_hash:
            _fail("CANON_HASH_MISMATCH")
        if expected_receipt_hash != receipt_hash:
            _fail("CANON_HASH_MISMATCH")

        # Raw artifact hash binding.
        pm_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=str(receipt.get("powermetrics_raw_path", "")))
        th_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=str(receipt.get("thermal_log_raw_path", "")))
        if not pm_path.exists() or not th_path.exists():
            _fail("MISSING_ARTIFACT")
        if sha256_file_prefixed(pm_path) != receipt.get("powermetrics_raw_hash"):
            _fail("CANON_HASH_MISMATCH")
        if sha256_file_prefixed(th_path) != receipt.get("thermal_log_raw_hash"):
            _fail("CANON_HASH_MISMATCH")

        receipts.append(receipt)
    return receipts


def _verify_stop_event(state_dir: Path, repo_root: Path, ledger_events: list[dict[str, Any]]) -> None:
    stop_events = [ev for ev in ledger_events if ev.get("event_type") == "THERMO_STOP"]
    if len(stop_events) != 1:
        _fail("SCHEMA_INVALID")
    payload = stop_events[0].get("payload") or {}
    if payload.get("stop_kind") != "EXTERNAL_SIGNAL":
        _fail("SCHEMA_INVALID")
    stop_path_s = payload.get("stop_provenance_path")
    stop_hash = payload.get("stop_provenance_hash")
    if not isinstance(stop_path_s, str) or not isinstance(stop_hash, str):
        _fail("SCHEMA_INVALID")
    stop_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=stop_path_s)
    if not stop_path.exists():
        _fail("MISSING_ARTIFACT")
    if sha256_file_prefixed(stop_path) != stop_hash:
        _fail("CANON_HASH_MISMATCH")


def _verify_promotion_chain(state_dir: Path, repo_root: Path, pack: dict[str, Any], ledger_events: list[dict[str, Any]]) -> None:
    cfg = pack.get("self_improvement") or {}
    enabled = bool(cfg.get("enabled"))
    max_promos = int(cfg.get("max_promotions_per_checkpoint", 0))
    if not enabled or max_promos <= 0:
        return

    evals = [ev for ev in ledger_events if ev.get("event_type") == "THERMO_PROMOTION_EVAL_RESULT"]
    accepted = [ev for ev in evals if (ev.get("payload") or {}).get("decision") == "ACCEPT"]
    if not accepted:
        _fail("SCHEMA_INVALID")

    checkpoints = [ev for ev in ledger_events if ev.get("event_type") == "THERMO_CHECKPOINT_WRITE"]
    applies = [ev for ev in ledger_events if ev.get("event_type") == "THERMO_PROMOTION_APPLY"]

    for ev in accepted:
        payload = ev.get("payload") or {}
        proposal_id = payload.get("proposal_id")
        proposal_path_s = payload.get("proposal_path")
        dev_gate_path_s = payload.get("dev_gate_receipt_path")
        if not isinstance(proposal_id, str) or not isinstance(proposal_path_s, str) or not isinstance(dev_gate_path_s, str):
            _fail("SCHEMA_INVALID")
        proposal_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=proposal_path_s)
        dev_gate_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=dev_gate_path_s)
        if not proposal_path.exists() or not dev_gate_path.exists():
            _fail("MISSING_ARTIFACT")

        # Find matching APPLY event for this proposal.
        match_apply = None
        for ap in applies:
            ap_payload = ap.get("payload") or {}
            if ap_payload.get("proposal_id") == proposal_id:
                match_apply = ap_payload
                break
        if match_apply is None:
            _fail("SCHEMA_INVALID")
        bundle_path_s = match_apply.get("promotion_bundle_path")
        bundle_id = match_apply.get("promotion_bundle_id")
        if not isinstance(bundle_path_s, str) or not isinstance(bundle_id, str):
            _fail("SCHEMA_INVALID")
        bundle_path = resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=bundle_path_s)
        if not bundle_path.exists():
            _fail("MISSING_ARTIFACT")

        bundle = load_required_canon_json(bundle_path)
        if bundle.get("schema") != "thermo_promotion_bundle_v1" or bundle.get("spec_version") != "v5_0":
            _fail("SCHEMA_INVALID")
        expected_bundle_id = sha256_prefixed(canon_bytes({k: v for k, v in bundle.items() if k != "bundle_id"}))
        if bundle.get("bundle_id") != expected_bundle_id or bundle_id != expected_bundle_id:
            _fail("CANON_HASH_MISMATCH")

        # Require at least one checkpoint that reflects active bundle id.
        if not any(((c.get("payload") or {}).get("active_promotion_bundle_id") == bundle_id) for c in checkpoints):
            _fail("SCHEMA_INVALID")


def verify(state_dir: Path) -> dict[str, Any]:
    # Phase A: identity + constitution
    constants = require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")
    repo_root = _repo_root_from_state_dir(state_dir)
    lock_path = repo_root / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    pack_path, pack = _find_pack(state_dir)
    if pack.get("pack_version") != "rsi_real_thermo_pack_v1":
        _fail("SCHEMA_INVALID")
    expected_pack_hash = compute_pack_hash(pack)
    root_cfg = pack.get("root") or {}
    if root_cfg.get("pack_hash") != expected_pack_hash:
        _fail("CANON_HASH_MISMATCH")

    identities = meta_identities()
    if root_cfg.get("required_icore_id") != lock.get("core_id"):
        _fail("ICORE_MISMATCH")
    if root_cfg.get("required_meta_hash") != identities.get("META_HASH"):
        _fail("META_HASH_MISMATCH")

    # Phase B: thermo ledger chain
    ledger_path = state_dir / "thermo" / "thermo_ledger_v1.jsonl"
    events = load_thermo_ledger(ledger_path)
    validate_thermo_chain(events)

    # Phase C: toolchain manifest required
    _load_toolchain_manifest(state_dir, events)

    # Phase D: stop provenance required
    _verify_stop_event(state_dir, repo_root, events)

    # Phase E: probe receipts integrity
    receipts = _collect_probe_receipts(state_dir, repo_root, events)
    if not receipts:
        _fail("SCHEMA_INVALID")
    for r in receipts:
        status = r.get("probe_status")
        if status == "INVALID_PARSE":
            _fail("THERMO_POWER_PARSE_MISSING_FATAL")
        if status == "ABORT_THERMAL_CRITICAL":
            _fail("THERMO_THERMAL_CRITICAL_FATAL")

    # Phase F: compute density ratios deterministically
    probe_results: list[ProbeResult] = []
    for r in receipts:
        if r.get("probe_status") != "VALID":
            continue
        probe_results.append(ProbeResult(passes=int(r.get("passes", 0)), energy_mJ=int(r.get("energy_mJ", 0))))

    metrics_cfg = (pack.get("thermo") or {}).get("metrics") or {}
    thresh_num = int(metrics_cfg.get("density_ratio_threshold_num", 105))
    thresh_den = int(metrics_cfg.get("density_ratio_threshold_den", 100))
    consecutive_required = int(metrics_cfg.get("consecutive_windows_required", 4))
    consecutive, (med_num, med_den) = trailing_consecutive_meeting_threshold(
        probe_results,
        thresh_num=thresh_num,
        thresh_den=thresh_den,
        consecutive_required=consecutive_required,
    )

    # Phase G: promotion integrity (when enabled)
    _verify_promotion_chain(state_dir, repo_root, pack, events)

    return {
        "verdict": "VALID",
        "pack_path": str(pack_path),
        "pack_hash": expected_pack_hash,
        "icore_id": lock.get("core_id"),
        "meta_hash": identities.get("META_HASH"),
        "density_ratio_num": int(med_num),
        "density_ratio_den": int(med_den),
        "consecutive_windows": int(consecutive),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = verify(Path(args.state_dir))
    except CanonError as exc:
        print(f"INVALID: {exc}")
        return 2
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
