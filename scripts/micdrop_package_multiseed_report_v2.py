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
