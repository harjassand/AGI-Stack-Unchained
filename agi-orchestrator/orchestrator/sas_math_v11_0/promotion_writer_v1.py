"""Promotion bundle writer for SAS-MATH (v11.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v11_0.fixed_q32_v1 import parse_q32


def _compute_bundle_id(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("bundle_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _acceptance(
    *,
    min_util_delta: int,
    min_eff_delta: int,
    max_regress: int,
    require_novelty: bool,
    min_novelty: int,
    baseline_util: int,
    candidate_util: int,
    baseline_eff: int,
    candidate_eff: int,
    novelty_score: int,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    delta_u = candidate_util - baseline_util
    delta_e = candidate_eff - baseline_eff
    if delta_u < -max_regress:
        reasons.append("UTILITY_REGRESSION_EXCEEDS_MAX")
    if not (delta_u >= min_util_delta or delta_e >= min_eff_delta):
        reasons.append("DOMINANCE_NOT_MET")
    if require_novelty and novelty_score < min_novelty:
        reasons.append("NOVELTY_REQUIRED_NOT_MET")
    return len(reasons) == 0, reasons


def write_promotion_bundle(
    *,
    promo_dir: Path,
    baseline_policy_id: str,
    baseline_fingerprint_hash: str,
    baseline_eval_report_hash: str,
    baseline_utility_q32: dict[str, Any],
    baseline_capacity_eff_q32: dict[str, Any],
    candidate_policy_id: str,
    candidate_fingerprint_hash: str,
    candidate_eval_report_hash_dev: str,
    candidate_eval_report_hash_heldout: str,
    candidate_utility_q32: dict[str, Any],
    candidate_capacity_eff_q32: dict[str, Any],
    thresholds: dict[str, Any],
    novelty_score_q32: dict[str, Any],
    improved_problem_ids: list[str],
    improvement_evidence: list[dict[str, Any]],
) -> Path:
    promo_dir.mkdir(parents=True, exist_ok=True)

    min_util_delta = parse_q32(thresholds.get("min_utility_delta_q32"))
    min_eff_delta = parse_q32(thresholds.get("min_efficiency_delta_q32"))
    max_regress = parse_q32(thresholds.get("max_utility_regression_q32"))
    min_novelty = parse_q32(thresholds.get("min_novelty_q32"))
    require_novelty = bool(thresholds.get("require_novelty"))

    baseline_util = parse_q32(baseline_utility_q32)
    candidate_util = parse_q32(candidate_utility_q32)
    baseline_eff = parse_q32(baseline_capacity_eff_q32)
    candidate_eff = parse_q32(candidate_capacity_eff_q32)
    novelty_score = parse_q32(novelty_score_q32)

    passed, reasons = _acceptance(
        min_util_delta=min_util_delta,
        min_eff_delta=min_eff_delta,
        max_regress=max_regress,
        require_novelty=require_novelty,
        min_novelty=min_novelty,
        baseline_util=baseline_util,
        candidate_util=candidate_util,
        baseline_eff=baseline_eff,
        candidate_eff=candidate_eff,
        novelty_score=novelty_score,
    )

    bundle = {
        "schema_version": "sas_math_promotion_bundle_v1",
        "bundle_id": "",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "acceptance_decision": {"pass": passed, "reasons": reasons},
        "baseline_policy_id": baseline_policy_id,
        "baseline_fingerprint_hash": baseline_fingerprint_hash,
        "baseline_utility_q32": baseline_utility_q32,
        "baseline_capacity_efficiency_q32": baseline_capacity_eff_q32,
        "baseline_eval_report_sha256": baseline_eval_report_hash,
        "candidate_policy_id": candidate_policy_id,
        "candidate_fingerprint_hash": candidate_fingerprint_hash,
        "candidate_utility_q32": candidate_utility_q32,
        "candidate_capacity_efficiency_q32": candidate_capacity_eff_q32,
        "candidate_eval_report_sha256_dev": candidate_eval_report_hash_dev,
        "candidate_eval_report_sha256_heldout": candidate_eval_report_hash_heldout,
        "require_novelty": require_novelty,
        "min_novelty_q32": thresholds.get("min_novelty_q32"),
        "novelty_score_q32": novelty_score_q32,
        "min_utility_delta_q32": thresholds.get("min_utility_delta_q32"),
        "min_efficiency_delta_q32": thresholds.get("min_efficiency_delta_q32"),
        "max_utility_regression_q32": thresholds.get("max_utility_regression_q32"),
        "improved_problem_ids": list(improved_problem_ids),
        "improvement_evidence": list(improvement_evidence),
    }
    bundle["bundle_id"] = _compute_bundle_id(bundle)
    path = promo_dir / f"sha256_{bundle['bundle_id'].split(':',1)[1]}.sas_math_promotion_bundle_v1.json"
    write_canon_json(path, bundle)
    return path


__all__ = ["write_promotion_bundle"]
