#!/usr/bin/env python3
"""Aggregate micdrop novelty per-seed evidence into a multiseed report."""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json

_Q32_ONE = 1 << 32
_Q32_085 = 3650722201
_MARKER_RE = re.compile(r"^# MICDROP_CAPABILITY_LEVEL:(\d+)\s*$", re.MULTILINE)
_SUITE_FAMILIES = ("arith", "numbertheory", "graph", "string", "dsl")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _read_solver_level(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    match = _MARKER_RE.search(text)
    return int(match.group(1)) if match else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="micdrop_package_multiseed_report_v2")
    parser.add_argument("--input_glob", default="runs/micdrop_novelty/*/MICDROP_SEED_EVIDENCE_v2.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--solver_path", default="tools/omega/agi_micdrop_solver_v1.py")
    return parser.parse_args()


def _suite_family_from_row(row: dict[str, Any]) -> str:
    suite_name = str(row.get("suite_name", "")).strip().lower()
    for family in _SUITE_FAMILIES:
        suffix = f"_{family}"
        if suite_name.endswith(suffix):
            return family
    suite_id = str(row.get("suite_id", "")).strip().lower()
    for family in _SUITE_FAMILIES:
        if family in suite_id:
            return family
    return "unknown"


def _is_sha256(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _sha_or_none(value: Any) -> str | None:
    text = str(value).strip()
    return text if _is_sha256(text) else None


def _family_mean_accuracy_q32(suites: list[Any]) -> dict[str, int]:
    by_family: dict[str, list[int]] = {}
    for row in suites:
        if not isinstance(row, dict):
            continue
        fam = _suite_family_from_row(row)
        acc = int(row.get("accuracy_q32", 0))
        by_family.setdefault(fam, []).append(acc)
    out: dict[str, int] = {}
    for fam, values in by_family.items():
        if not values:
            continue
        out[fam] = int(sum(values) // len(values))
    return out


def main() -> int:
    args = _parse_args()
    evidence_paths = sorted(Path(path).resolve() for path in glob.glob(str(args.input_glob)))
    if not evidence_paths:
        raise RuntimeError("no seed evidence files matched input_glob")

    rows: list[dict[str, Any]] = []
    for path in evidence_paths:
        payload = _load_json(path)
        rows.append(payload)

    rows.sort(key=lambda row: int(row.get("seed_u64", 0)))
    seeds = [int(row.get("seed_u64", 0)) for row in rows]
    suite_set_ids = [str(row.get("suite_set_id", "")) for row in rows]

    seed_metrics: list[dict[str, Any]] = []
    deltas: list[int] = []
    improved_u64 = 0
    total_promotions = 0
    per_seed_promotions: dict[str, int] = {}
    per_suite_high_hits: dict[str, int] = {}
    per_family_high_hits: dict[str, int] = {}
    breadth_seed_hits_u64 = 0
    frozen_hash_fail_seeds: list[int] = []
    accelerator_evidence_per_seed: list[dict[str, Any]] = []
    cross_domain_delta_accum: dict[str, list[int]] = {}
    objective_j_dominance_checks_set: set[str] = set()
    nontriviality_cert_hashes_set: set[str] = set()
    operator_bank_hashes_seen: set[str] = set()
    active_inference_reduce_hashes_seen: set[str] = set()
    metal_soak_receipt_hashes_seen: set[str] = set()

    for row in rows:
        seed = int(row.get("seed_u64", 0))
        baseline = dict(row.get("baseline") or {})
        after = dict(row.get("after") or {})
        promotions = dict(row.get("promotions") or {})
        frozen_hash_check = dict(row.get("frozen_hash_check") or {})
        baseline_accuracy_q32 = int(baseline.get("mean_accuracy_q32", 0))
        baseline_coverage_q32 = int(baseline.get("mean_coverage_q32", 0))
        after_accuracy_q32 = int(after.get("mean_accuracy_q32", 0))
        after_coverage_q32 = int(after.get("mean_coverage_q32", 0))
        delta_accuracy_q32 = int(after_accuracy_q32 - baseline_accuracy_q32)
        delta_coverage_q32 = int(after_coverage_q32 - baseline_coverage_q32)
        if delta_accuracy_q32 > 0:
            improved_u64 += 1
        deltas.append(delta_accuracy_q32)

        if not bool(frozen_hash_check.get("unchanged_b", False)):
            frozen_hash_fail_seeds.append(seed)

        seed_promo_u64 = int(promotions.get("accepted_promotions_u64", 0))
        total_promotions += seed_promo_u64
        per_seed_promotions[str(seed)] = seed_promo_u64

        after_suites = list(after.get("suites") or [])
        suites_above_u64 = 0
        seen_families_this_seed: set[str] = set()
        for suite_row in after_suites:
            if not isinstance(suite_row, dict):
                continue
            suite_name = str(suite_row.get("suite_name", "")).strip() or str(suite_row.get("suite_id", "")).strip()
            accuracy_q32 = int(suite_row.get("accuracy_q32", 0))
            if accuracy_q32 >= _Q32_085:
                suites_above_u64 += 1
                per_suite_high_hits[suite_name] = int(per_suite_high_hits.get(suite_name, 0)) + 1
                family = _suite_family_from_row(suite_row)
                if family not in seen_families_this_seed:
                    per_family_high_hits[family] = int(per_family_high_hits.get(family, 0)) + 1
                    seen_families_this_seed.add(family)
        if suites_above_u64 >= 3:
            breadth_seed_hits_u64 += 1

        baseline_fam_means = _family_mean_accuracy_q32(list(baseline.get("suites") or []))
        after_fam_means = _family_mean_accuracy_q32(list(after.get("suites") or []))
        fam_union = sorted(set(baseline_fam_means.keys()) | set(after_fam_means.keys()))
        for fam in fam_union:
            delta_fam = int(after_fam_means.get(fam, 0) - baseline_fam_means.get(fam, 0))
            cross_domain_delta_accum.setdefault(fam, []).append(delta_fam)

        accelerators = dict(row.get("accelerators") or {})
        grpo_best = dict(row.get("grpo_best") or accelerators.get("grpo_best") or {})
        applied_promotions = list(promotions.get("applied_promotions") or [])
        grpo_best_candidate_hash = _sha_or_none(grpo_best.get("best_candidate_hash"))
        if grpo_best_candidate_hash is None:
            for promo in applied_promotions:
                if not isinstance(promo, dict):
                    continue
                grpo_best_candidate_hash = _sha_or_none(
                    promo.get("best_candidate_hash")
                    or promo.get("candidate_bundle_hash")
                    or promo.get("promotion_id")
                )
                if grpo_best_candidate_hash is not None:
                    break
        grpo_best_cac_reward_q32 = int(grpo_best.get("best_cac_reward_q32", grpo_best.get("cac_reward_q32", 0)))

        operator_bank = dict(row.get("operator_bank") or accelerators.get("operator_bank") or {})
        operator_bank_hash = _sha_or_none(operator_bank.get("bank_hash") or operator_bank.get("operator_bank_hash"))
        operator_bank_tokens = sorted(
            {
                str(tok).strip()
                for tok in list(operator_bank.get("tokens") or operator_bank.get("token_list") or [])
                if str(tok).strip()
            }
        )
        if operator_bank_hash is not None:
            operator_bank_hashes_seen.add(operator_bank_hash)

        active_inference = dict(row.get("active_inference") or accelerators.get("active_inference") or {})
        uncertainty_report_hash = _sha_or_none(active_inference.get("uncertainty_report_hash"))
        sip_receipt_hash = _sha_or_none(active_inference.get("sip_receipt_hash"))
        reduce_receipt_hash = _sha_or_none(active_inference.get("reduce_receipt_hash"))
        active_inference_receipt_hash = _sha_or_none(active_inference.get("active_inference_receipt_hash"))
        utility_proof_hash = _sha_or_none(active_inference.get("utility_proof_hash"))
        if reduce_receipt_hash is not None:
            active_inference_reduce_hashes_seen.add(reduce_receipt_hash)

        native_shadow = dict(
            row.get("native_shadow_soak")
            or row.get("native_shadow")
            or accelerators.get("native_shadow_soak")
            or {}
        )
        wasm_soak_receipt_hash = _sha_or_none(native_shadow.get("wasm_soak_receipt_hash") or native_shadow.get("wasm_only_receipt_hash"))
        metal_soak_receipt_hash = _sha_or_none(
            native_shadow.get("metal_soak_receipt_hash")
            or native_shadow.get("wasm_vs_metal_soak_receipt_hash")
        )
        if metal_soak_receipt_hash is not None:
            metal_soak_receipt_hashes_seen.add(metal_soak_receipt_hash)

        objective_j = dict(row.get("objective_j") or accelerators.get("objective_j") or {})
        dominance_hashes = sorted(
            {
                str(v).strip()
                for v in list(objective_j.get("dominance_check_hashes") or objective_j.get("objective_j_dominance_checks") or [])
                if _is_sha256(v)
            }
        )
        nontriviality_hashes = sorted(
            {
                str(v).strip()
                for v in list(objective_j.get("nontriviality_cert_hashes") or [])
                if _is_sha256(v)
            }
        )
        objective_j_dominance_checks_set.update(dominance_hashes)
        nontriviality_cert_hashes_set.update(nontriviality_hashes)

        accelerator_evidence_per_seed.append(
            {
                "seed_u64": seed,
                "grpo_best_candidate_hash": grpo_best_candidate_hash,
                "grpo_best_cac_reward_q32": int(grpo_best_cac_reward_q32),
                "operator_bank_hash": operator_bank_hash,
                "operator_bank_tokens": operator_bank_tokens,
                "active_inference_receipt_hashes": {
                    "uncertainty_report_hash": uncertainty_report_hash,
                    "sip_receipt_hash": sip_receipt_hash,
                    "reduce_receipt_hash": reduce_receipt_hash,
                    "active_inference_receipt_hash": active_inference_receipt_hash,
                    "utility_proof_hash": utility_proof_hash,
                },
                "native_shadow_soak_receipts": {
                    "wasm_only_receipt_hash": wasm_soak_receipt_hash,
                    "wasm_vs_metal_receipt_hash": metal_soak_receipt_hash,
                },
                "objective_j_dominance_check_hashes": dominance_hashes,
                "nontriviality_cert_hashes": nontriviality_hashes,
            }
        )

        seed_metrics.append(
            {
                "seed_u64": seed,
                "suite_set_id": str(row.get("suite_set_id", "")),
                "baseline_accuracy_q32": baseline_accuracy_q32,
                "after_accuracy_q32": after_accuracy_q32,
                "delta_accuracy_q32": delta_accuracy_q32,
                "baseline_coverage_q32": baseline_coverage_q32,
                "after_coverage_q32": after_coverage_q32,
                "delta_coverage_q32": delta_coverage_q32,
                "accepted_promotions_u64": seed_promo_u64,
                "activation_success_u64": int(promotions.get("activation_success_u64", 0)),
            }
        )

    mean_delta_accuracy_q32 = int(sum(deltas) // len(deltas)) if deltas else 0
    fraction_improved_q32 = int((int(improved_u64) * _Q32_ONE) // max(1, len(rows)))
    distinct_suite_set_ids_u64 = len(set(suite_set_ids))
    breadth_suite_hits_u64 = int(sum(1 for family, hits in per_family_high_hits.items() if family in _SUITE_FAMILIES and hits >= 3))
    cross_domain_performance_deltas_q32 = {
        str(fam): int(sum(vals) // len(vals))
        for fam, vals in sorted(cross_domain_delta_accum.items())
        if vals
    }

    multi_seed_consistency_summary = {
        "operator_bank_hash_consistent_b": len(operator_bank_hashes_seen) <= 1,
        "active_inference_reduce_receipt_consistent_b": len(active_inference_reduce_hashes_seen) <= 1,
        "metal_soak_receipt_consistent_b": len(metal_soak_receipt_hashes_seen) <= 1,
        "operator_bank_hashes_observed_u64": int(len(operator_bank_hashes_seen)),
        "active_inference_reduce_receipts_observed_u64": int(len(active_inference_reduce_hashes_seen)),
        "metal_soak_receipts_observed_u64": int(len(metal_soak_receipt_hashes_seen)),
    }

    solver_level = _read_solver_level((_REPO_ROOT / str(args.solver_path)).resolve())

    report = {
        "schema_version": "micdrop_novelty_multi_seed_report_v2",
        "seeds": seeds,
        "seed_metrics": seed_metrics,
        "distinct_suite_set_ids_u64": int(distinct_suite_set_ids_u64),
        "mean_delta_accuracy_q32": int(mean_delta_accuracy_q32),
        "fraction_improved_q32": int(fraction_improved_q32),
        "improved_seeds_u64": int(improved_u64),
        "total_seeds_u64": int(len(rows)),
        "total_accepted_promotions_u64": int(total_promotions),
        "accepted_promotions_per_seed": per_seed_promotions,
        "accelerator_evidence_per_seed": accelerator_evidence_per_seed,
        "cross_domain_performance_deltas_q32": cross_domain_performance_deltas_q32,
        "multi_seed_consistency_summary": multi_seed_consistency_summary,
        "objective_j_dominance_checks": sorted(objective_j_dominance_checks_set),
        "nontriviality_cert_hashes": sorted(nontriviality_cert_hashes_set),
        "breadth": {
            "suite_accuracy_threshold_q32": int(_Q32_085),
            "seeds_with_at_least_3_suites_ge_threshold_u64": int(breadth_seed_hits_u64),
            "suites_with_at_least_3_seed_hits_u64": int(breadth_suite_hits_u64),
            "per_suite_family_high_hits_u64": {str(k): int(v) for k, v in sorted(per_family_high_hits.items())},
            "per_suite_high_hits_u64": {str(k): int(v) for k, v in sorted(per_suite_high_hits.items())},
        },
        "no_evaluator_cheating": {
            "frozen_hash_checks_all_passed_b": len(frozen_hash_fail_seeds) == 0,
            "frozen_hash_failed_seed_u64s": sorted(frozen_hash_fail_seeds),
        },
        "final_solver_capability_level": int(solver_level),
    }

    out_path = Path(str(args.out)).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, report)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
