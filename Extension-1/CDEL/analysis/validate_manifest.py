"""Validate suite manifest schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_CLAIMS = {
    "C1_non_interference",
    "C2_append_only",
    "C3_addressability",
    "C3_scan_baseline",
    "C4_capacity",
    "C5_certificate_knob",
    "C6_reuse_control",
    "C7_cache_equivalence",
    "C8_hygiene",
}

ALLOWED_KEYS = {
    "required",
    "audit_full_runs",
    "audit_fast_runs",
    "runs",
    "run",
    "indexed_run",
    "scan_run",
    "bounded_run",
    "proof_run",
    "baseline_run",
    "cache_run",
    "reuse_run",
    "max_median_closure_ratio",
    "max_closure_slope",
    "min_scan_to_indexed_ratio",
    "min_capacity_reject_ratio",
    "min_proof_total_nodes",
    "min_proof_reject_ratio",
    "min_reuse_rate_delta",
    "min_reuse_ratio_delta",
    "min_unused_fraction_delta",
    "min_symbols_per_task_delta",
}


def validate_manifest(manifest: dict, path: Path | None = None) -> dict:
    if not isinstance(manifest, dict):
        _fail("manifest must be a JSON object", path)
    for key in ("suite_name", "claim_complete", "claims"):
        if key not in manifest:
            _fail(f"manifest missing required field: {key}", path)
    if not isinstance(manifest["suite_name"], str) or not manifest["suite_name"]:
        _fail("suite_name must be a non-empty string", path)
    if not isinstance(manifest["claim_complete"], bool):
        _fail("claim_complete must be a boolean", path)
    claims = manifest["claims"]
    if not isinstance(claims, dict):
        _fail("claims must be an object", path)
    for claim_id, cfg in claims.items():
        if claim_id not in ALLOWED_CLAIMS:
            _fail(f"unknown claim id: {claim_id}", path)
        if not isinstance(cfg, dict):
            _fail(f"claim {claim_id} must be an object", path)
        _validate_claim_cfg(claim_id, cfg, path)
    return manifest


def _validate_claim_cfg(claim_id: str, cfg: dict, path: Path | None) -> None:
    for key, value in cfg.items():
        if key not in ALLOWED_KEYS:
            _fail(f"claim {claim_id} has unknown key: {key}", path)
        if key in {"audit_full_runs", "audit_fast_runs", "runs"}:
            _expect_list_of_str(key, value, claim_id, path)
        elif key in {
            "run",
            "indexed_run",
            "scan_run",
            "bounded_run",
            "proof_run",
            "baseline_run",
            "cache_run",
            "reuse_run",
        }:
            _expect_str(key, value, claim_id, path)
        elif key == "required":
            if not isinstance(value, bool):
                _fail(f"claim {claim_id} {key} must be boolean", path)
        else:
            if not isinstance(value, (int, float)):
                _fail(f"claim {claim_id} {key} must be numeric", path)


def _expect_list_of_str(key: str, value, claim_id: str, path: Path | None) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        _fail(f"claim {claim_id} {key} must be a non-empty list of strings", path)


def _expect_str(key: str, value, claim_id: str, path: Path | None) -> None:
    if not isinstance(value, str) or not value:
        _fail(f"claim {claim_id} {key} must be a non-empty string", path)


def _fail(msg: str, path: Path | None) -> None:
    prefix = f"{path}: " if path else ""
    raise SystemExit(prefix + msg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    path = Path(args.manifest)
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data, path)
    print("ok")


if __name__ == "__main__":
    main()
