"""Verifier for RSI Alignment (v7.0, Superego Protocol v1)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v2_3.immutable_core import load_lock, validate_lock
from .alignment_eval import compute_alignment_report_hash, load_alignment_report, load_clearance_receipt
from .superego_ledger import load_superego_ledger, validate_superego_chain
from .superego_policy import compute_policy_hash, load_policy


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _meta_core_root() -> Path:
    env_override = Path(os.environ.get("META_CORE_ROOT", "")) if os.environ.get("META_CORE_ROOT") else None
    if env_override and env_override.exists():
        return env_override
    return Path(__file__).resolve().parents[3] / "meta-core"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _require_constants() -> dict[str, Any]:
    meta_root = _meta_core_root()
    constants_path = meta_root / "meta_constitution" / "v7_0" / "constants_v1.json"
    return load_canon_json(constants_path)


def _meta_identities() -> dict[str, str]:
    meta_root = _meta_core_root()
    meta_hash = _read_text(meta_root / "meta_constitution" / "v7_0" / "META_HASH")
    kernel_hash = _read_text(meta_root / "kernel" / "verifier" / "KERNEL_HASH")
    constants_hash = sha256_prefixed(canon_bytes(_require_constants()))
    return {
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
    }


def _require_pack(config_dir: Path) -> dict[str, Any]:
    pack_path = config_dir / "rsi_alignment_pack_v1.json"
    if not pack_path.exists():
        _fail("MISSING_ARTIFACT")
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_alignment_pack_v1":
        _fail("SCHEMA_INVALID")
    for key in ["icore_id", "meta_hash", "policy_hash", "sealed_alignment_config", "clearance_thresholds"]:
        if key not in pack:
            _fail("SCHEMA_INVALID")
    return pack


def _require_thresholds(pack: dict[str, Any]) -> tuple[int, int, int]:
    thresholds = pack.get("clearance_thresholds")
    if not isinstance(thresholds, dict):
        _fail("SCHEMA_INVALID")
    min_num = thresholds.get("min_align_score_num")
    min_den = thresholds.get("min_align_score_den")
    hard_fail_max = thresholds.get("hard_fail_max")
    if not isinstance(min_num, int) or not isinstance(min_den, int) or not isinstance(hard_fail_max, int):
        _fail("SCHEMA_INVALID")
    if min_den <= 0 or min_num < 0 or hard_fail_max < 0:
        _fail("SCHEMA_INVALID")
    return min_num, min_den, hard_fail_max


def verify(alignment_dir: Path, *, mode: str) -> dict[str, Any]:
    constants = _require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")

    repo_root = Path(__file__).resolve().parents[3]
    lock_path = repo_root / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    identities = _meta_identities()
    expected_icore = str(lock.get("core_id"))
    expected_meta = identities.get("META_HASH")

    daemon_root = alignment_dir.parent.parent
    config_dir = daemon_root / "config"
    pack = _require_pack(config_dir)

    if pack.get("icore_id") != expected_icore or pack.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")

    policy_path = alignment_dir / "policy" / "superego_policy_v1.json"
    policy_lock_path = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy = load_policy(policy_path)
    policy_hash = compute_policy_hash(policy)

    if pack.get("policy_hash") != policy_hash:
        _fail("POLICY_HASH_MISMATCH")

    if not policy_lock_path.exists():
        _fail("MISSING_ARTIFACT")
    policy_lock = load_canon_json(policy_lock_path)
    if not isinstance(policy_lock, dict) or policy_lock.get("schema_version") != "superego_policy_lock_v1":
        _fail("SCHEMA_INVALID")
    if policy_lock.get("superego_policy_hash") != policy_hash:
        _fail("POLICY_HASH_MISMATCH")
    if policy_lock.get("icore_id") != expected_icore or policy_lock.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    entries = load_superego_ledger(ledger_path)
    head_hash, _last_tick, _last_seq = validate_superego_chain(entries)

    report_path = alignment_dir / "reports" / "alignment_report_v1.json"
    report = load_alignment_report(report_path)
    if report.get("policy_hash") != policy_hash:
        _fail("POLICY_HASH_MISMATCH")
    if report.get("icore_id") != expected_icore or report.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")

    report_hash = compute_alignment_report_hash(report)

    receipt_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    receipt = load_clearance_receipt(receipt_path)
    if receipt.get("policy_hash") != policy_hash:
        _fail("POLICY_HASH_MISMATCH")
    if receipt.get("icore_id") != expected_icore or receipt.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")
    if receipt.get("alignment_report_hash") != report_hash:
        _fail("CANON_HASH_MISMATCH")
    if receipt.get("ledger_head_hash") != head_hash:
        _fail("CANON_HASH_MISMATCH")

    min_num, min_den, hard_fail_max = _require_thresholds(pack)
    hard_fail_count = report.get("hard_fail_count")
    if not isinstance(hard_fail_count, int):
        _fail("SCHEMA_INVALID")
    if hard_fail_count > hard_fail_max:
        _fail("ALIGNMENT_THRESHOLD_FAIL")

    score_num = report.get("align_score_num")
    score_den = report.get("align_score_den")
    if not isinstance(score_num, int) or not isinstance(score_den, int) or score_den <= 0:
        _fail("SCHEMA_INVALID")
    if score_num * min_den < min_num * score_den:
        _fail("ALIGNMENT_THRESHOLD_FAIL")

    if mode not in {"clearance_only", "full"}:
        _fail("SCHEMA_INVALID")

    return {"status": "VALID", "policy_hash": policy_hash, "ledger_head_hash": head_hash}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI alignment artifacts v7.0")
    parser.add_argument("--alignment_dir", required=True)
    parser.add_argument("--mode", default="full", choices=["clearance_only", "full"])
    args = parser.parse_args()
    try:
        verify(Path(args.alignment_dir), mode=args.mode)
    except CanonError as exc:
        print(f"INVALID: {exc}")
        raise SystemExit(1) from exc
    print("VALID")


if __name__ == "__main__":
    main()
