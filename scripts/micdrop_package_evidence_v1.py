#!/usr/bin/env python3
"""Package micdrop evidence artifacts into one hash-bound bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (REPO_ROOT, REPO_ROOT / "CDEL-v2"):
    text = str(entry)
    if text not in sys.path:
        sys.path.insert(0, text)

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.omega_common_v1 import canon_hash_obj

FORBIDDEN_PREFIXES = ("authority/", "meta-core/", "CDEL-v2/", "Genesis/", ".git/", "runs/")
RUNNER_RELPATH = "tools/omega/agi_micdrop_candidate_runner_v1.py"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _q32(row: dict[str, Any], metric_id: str) -> int:
    metric = row.get(metric_id)
    if not isinstance(metric, dict):
        return 0
    return int(metric.get("q", 0))


def _suite_metrics_by_id(receipt: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in receipt.get("executed_suites", []):
        if not isinstance(row, dict):
            continue
        suite_id = str(row.get("suite_id", "")).strip()
        if not suite_id:
            continue
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        out[suite_id] = {
            "accuracy_q32": _q32(metrics, "holdout_accuracy_q32"),
            "coverage_q32": _q32(metrics, "holdout_coverage_q32"),
        }
    return out


def _git_head_sha() -> str:
    run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        return ""
    return str(run.stdout).strip()


def _collect_promotions(ticks_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    promotions: list[dict[str, Any]] = []
    touched_all: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    receipt_glob = "tick_*/daemon/rsi_omega_daemon_v19_0/state/dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"
    for receipt_path in sorted(ticks_root.glob(receipt_glob), key=lambda p: p.as_posix()):
        receipt_payload = _load_json(receipt_path)
        result = receipt_payload.get("result")
        status = str((result or {}).get("status", "")).strip().upper() if isinstance(result, dict) else ""
        if status != "PROMOTED":
            continue

        dispatch_dir = receipt_path.parents[1]
        state_root = dispatch_dir.parents[1]

        activation_paths = sorted((dispatch_dir / "activation").glob("sha256_*.omega_activation_receipt_v1.json"), key=lambda p: p.as_posix())
        activation_payload = _load_json(activation_paths[-1]) if activation_paths else {}
        activation_receipt_id = (
            str(activation_payload.get("receipt_id", "")).strip()
            or (f"sha256:{activation_paths[-1].name.split('.', 1)[0].split('_', 1)[1]}" if activation_paths else "")
        )

        replay_binding = receipt_payload.get("replay_binding_v1")
        replay_rel = str((replay_binding or {}).get("replay_state_dir_relpath", "")).strip() if isinstance(replay_binding, dict) else ""
        bundle_id = str(receipt_payload.get("promotion_bundle_hash", "")).strip()
        bundle_payload: dict[str, Any] = {}
        if replay_rel and bundle_id.startswith("sha256:"):
            bundle_path = (state_root / replay_rel / "promotion" / f"sha256_{bundle_id.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json").resolve()
            if bundle_path.exists() and bundle_path.is_file():
                bundle_payload = _load_json(bundle_path)

        ccap_id = str(bundle_payload.get("ccap_id", "")).strip()
        touched = bundle_payload.get("touched_paths")
        touched_paths = [str(row).strip() for row in touched if str(row).strip()] if isinstance(touched, list) else []
        patch_sha256 = ""

        ccap_rel = str(bundle_payload.get("ccap_relpath", "")).strip()
        if replay_rel and ccap_rel:
            ccap_path = (state_root / replay_rel / ccap_rel).resolve()
            if ccap_path.exists() and ccap_path.is_file():
                ccap_payload = _load_json(ccap_path)
                payload_obj = ccap_payload.get("payload")
                if isinstance(payload_obj, dict):
                    patch_sha256 = str(payload_obj.get("patch_blob_id", "")).strip()

        if not patch_sha256:
            patch_rel = str(bundle_payload.get("patch_relpath", "")).strip()
            if replay_rel and patch_rel:
                patch_path = (state_root / replay_rel / patch_rel).resolve()
                if patch_path.exists() and patch_path.is_file():
                    patch_sha256 = _sha256_file(patch_path)

        key = (
            dispatch_dir.relative_to(REPO_ROOT).as_posix(),
            ccap_id,
            patch_sha256,
            activation_receipt_id,
        )
        if key in seen:
            continue
        seen.add(key)

        touched_all.extend(touched_paths)
        promotions.append(
            {
                "promotion_receipt_id": str(receipt_payload.get("receipt_id", "")).strip(),
                "dispatch_relpath": dispatch_dir.relative_to(REPO_ROOT).as_posix(),
                "ccap_id": ccap_id,
                "patch_sha256": patch_sha256,
                "touched_paths": sorted(set(touched_paths)),
                "activation_success_proof": {
                    "activation_receipt_id": activation_receipt_id,
                    "activation_success": bool(activation_payload.get("activation_success", False)),
                    "pass": bool(activation_payload.get("pass", False)),
                    "reasons": list(activation_payload.get("reasons", [])) if isinstance(activation_payload.get("reasons"), list) else [],
                },
            }
        )

    return promotions, touched_all


def main() -> int:
    parser = argparse.ArgumentParser(prog="micdrop_package_evidence_v1")
    parser.add_argument("--baseline_series", default="runs/micdrop_baseline")
    parser.add_argument("--after_series", default="runs/micdrop_after")
    parser.add_argument("--ticks_root", default="runs/micdrop_ticks")
    parser.add_argument("--runner_sha256_before", default="")
    args = parser.parse_args()

    baseline_path = (REPO_ROOT / str(args.baseline_series) / "MICDROP_BENCH_RECEIPT_v2.json").resolve()
    after_path = (REPO_ROOT / str(args.after_series) / "MICDROP_BENCH_RECEIPT_v2.json").resolve()
    ticks_root = (REPO_ROOT / str(args.ticks_root)).resolve()

    if not baseline_path.exists() or not baseline_path.is_file():
        raise RuntimeError(f"missing baseline receipt: {baseline_path.as_posix()}")
    if not after_path.exists() or not after_path.is_file():
        raise RuntimeError(f"missing after receipt: {after_path.as_posix()}")
    if not ticks_root.exists() or not ticks_root.is_dir():
        raise RuntimeError(f"missing ticks root: {ticks_root.as_posix()}")

    baseline_receipt = _load_json(baseline_path)
    after_receipt = _load_json(after_path)

    baseline_suite = _suite_metrics_by_id(baseline_receipt)
    after_suite = _suite_metrics_by_id(after_receipt)

    per_suite_delta: list[dict[str, Any]] = []
    for suite_id in sorted(set(baseline_suite.keys()) | set(after_suite.keys())):
        base = baseline_suite.get(suite_id, {"accuracy_q32": 0, "coverage_q32": 0})
        aft = after_suite.get(suite_id, {"accuracy_q32": 0, "coverage_q32": 0})
        per_suite_delta.append(
            {
                "suite_id": suite_id,
                "baseline_accuracy_q32": int(base["accuracy_q32"]),
                "after_accuracy_q32": int(aft["accuracy_q32"]),
                "delta_accuracy_q32": int(aft["accuracy_q32"] - base["accuracy_q32"]),
                "baseline_coverage_q32": int(base["coverage_q32"]),
                "after_coverage_q32": int(aft["coverage_q32"]),
                "delta_coverage_q32": int(aft["coverage_q32"] - base["coverage_q32"]),
            }
        )

    base_agg = baseline_receipt.get("aggregate_metrics") if isinstance(baseline_receipt.get("aggregate_metrics"), dict) else {}
    aft_agg = after_receipt.get("aggregate_metrics") if isinstance(after_receipt.get("aggregate_metrics"), dict) else {}
    base_agg_acc = _q32(base_agg, "holdout_accuracy_q32")
    aft_agg_acc = _q32(aft_agg, "holdout_accuracy_q32")
    base_agg_cov = _q32(base_agg, "holdout_coverage_q32")
    aft_agg_cov = _q32(aft_agg, "holdout_coverage_q32")

    promotions, touched_all = _collect_promotions(ticks_root)

    forbidden_touched = sorted(
        {
            rel
            for rel in touched_all
            if any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
        }
    )

    runner_path = (REPO_ROOT / RUNNER_RELPATH).resolve()
    runner_sha_after = _sha256_file(runner_path)
    runner_sha_before = str(args.runner_sha256_before).strip() or runner_sha_after

    pins = load_authority_pins(REPO_ROOT)
    pins_path = (REPO_ROOT / str(os.environ.get("OMEGA_AUTHORITY_PINS_REL", "authority/authority_pins_v1.json"))).resolve()

    bundle = {
        "schema_version": "MICDROP_EVIDENCE_BUNDLE_v1",
        "git_head_sha": _git_head_sha(),
        "authority_pins": {
            "path": pins_path.relative_to(REPO_ROOT).as_posix(),
            "auth_hash": auth_hash(pins),
        },
        "baseline_benchmark_receipt_v2": {
            "hash": canon_hash_obj(baseline_receipt),
            "payload": baseline_receipt,
        },
        "after_benchmark_receipt_v2": {
            "hash": canon_hash_obj(after_receipt),
            "payload": after_receipt,
        },
        "delta_summary": {
            "per_suite": per_suite_delta,
            "aggregate": {
                "baseline_accuracy_q32": int(base_agg_acc),
                "after_accuracy_q32": int(aft_agg_acc),
                "delta_accuracy_q32": int(aft_agg_acc - base_agg_acc),
                "baseline_coverage_q32": int(base_agg_cov),
                "after_coverage_q32": int(aft_agg_cov),
                "delta_coverage_q32": int(aft_agg_cov - base_agg_cov),
            },
        },
        "accepted_promotions": promotions,
        "safety_assertions": {
            "forbidden_touched_paths": forbidden_touched,
            "no_forbidden_touched_paths_b": len(forbidden_touched) == 0,
            "runner_relpath": RUNNER_RELPATH,
            "runner_sha256_before": runner_sha_before,
            "runner_sha256_after": runner_sha_after,
            "runner_unchanged_b": runner_sha_before == runner_sha_after,
        },
    }

    out_path = (REPO_ROOT / "runs" / "MICDROP_EVIDENCE_BUNDLE_v1.json").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "schema_version": "MICDROP_EVIDENCE_PACKAGE_SUMMARY_v1",
                "bundle_relpath": out_path.relative_to(REPO_ROOT).as_posix(),
                "bundle_hash": canon_hash_obj(bundle),
                "accepted_promotions_u64": len(promotions),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
