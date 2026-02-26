#!/usr/bin/env python3
"""Aggregate oracle ladder per-seed evidence into one multiseed report."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_multiseed_report_v1")
    parser.add_argument("--input_glob", default="runs/oracle_ladder/*/ORACLE_SEED_EVIDENCE_v1.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--operator_bank_before", default="runs/oracle_ladder/operator_bank_baseline_v1.json")
    parser.add_argument("--operator_bank_after", default="daemon/oracle_ladder/operator_bank_active.json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    evidence_paths = sorted(Path(path).resolve() for path in glob.glob(str(args.input_glob)))
    if not evidence_paths:
        raise RuntimeError("no seed evidence files matched input_glob")

    rows = [_load_json(path) for path in evidence_paths]
    rows.sort(key=lambda row: int(row.get("seed_u64", 0)))

    per_seed: list[dict[str, Any]] = []
    delta_rows: list[int] = []
    all_promotions: list[dict[str, Any]] = []
    frozen_fail_seeds: list[int] = []

    for row in rows:
        seed = int(row.get("seed_u64", 0))
        baseline = dict(row.get("baseline") or {})
        after = dict(row.get("after") or {})
        promotions = dict(row.get("promotions") or {})
        frozen = dict(row.get("frozen_hash_check") or {})

        base_pass_q32 = int(baseline.get("mean_pass_rate_q32", 0))
        after_pass_q32 = int(after.get("mean_pass_rate_q32", 0))
        delta_q32 = int(after_pass_q32 - base_pass_q32)
        delta_rows.append(delta_q32)

        if not bool(frozen.get("unchanged_b", False)):
            frozen_fail_seeds.append(seed)

        promo_rows = list(promotions.get("applied_promotions") or [])
        for promo in promo_rows:
            if not isinstance(promo, dict):
                continue
            all_promotions.append(
                {
                    "seed_u64": int(seed),
                    "promotion_id": str(promo.get("promotion_id", "")),
                    "target_capability_level": int(promo.get("target_capability_level", 0)),
                    "activation_success_b": bool(promo.get("activation_success_b", False)),
                    "touched_paths": [str(path) for path in list(promo.get("touched_paths") or [])],
                }
            )

        per_seed.append(
            {
                "seed_u64": int(seed),
                "suite_set_id": str(row.get("suite_set_id", "")),
                "baseline_pass_rate_q32": int(base_pass_q32),
                "after_pass_rate_q32": int(after_pass_q32),
                "delta_pass_rate_q32": int(delta_q32),
                "baseline_coverage_q32": int(baseline.get("mean_coverage_q32", 0)),
                "after_coverage_q32": int(after.get("mean_coverage_q32", 0)),
                "accepted_promotions_u64": int(promotions.get("accepted_promotions_u64", 0)),
                "activation_success_u64": int(promotions.get("activation_success_u64", 0)),
            }
        )

    mean_delta_q32 = int(sum(delta_rows) // len(delta_rows)) if delta_rows else 0

    before_bank_path = Path(str(args.operator_bank_before)).resolve()
    after_bank_path = Path(str(args.operator_bank_after)).resolve()
    before_bank = _load_json(before_bank_path) if before_bank_path.exists() and before_bank_path.is_file() else {
        "operators": []
    }
    after_bank = _load_json(after_bank_path) if after_bank_path.exists() and after_bank_path.is_file() else {
        "operators": []
    }

    before_ops = list(before_bank.get("operators") or [])
    after_ops = list(after_bank.get("operators") or [])
    before_count = int(len([row for row in before_ops if isinstance(row, dict)]))

    valid_after = [row for row in after_ops if isinstance(row, dict)]
    after_count = int(len(valid_after))
    growth = int(max(0, after_count - before_count))

    ranked = sorted(
        valid_after,
        key=lambda row: (-int(row.get("usage_count_u64", 0)), str(row.get("op_name", ""))),
    )
    top10 = [
        {
            "op_name": str(row.get("op_name", "")),
            "usage_count_u64": int(row.get("usage_count_u64", 0)),
            "added_from_task_id": str(row.get("added_from_task_id", "")),
        }
        for row in ranked[:10]
    ]

    report = {
        "schema_version": "oracle_ladder_multi_seed_report_v1",
        "seeds": [int(row.get("seed_u64", 0)) for row in per_seed],
        "per_seed": per_seed,
        "aggregate": {
            "mean_delta_pass_rate_q32": int(mean_delta_q32),
            "total_seeds_u64": int(len(per_seed)),
            "accepted_promotions_u64": int(len(all_promotions)),
            "activation_success_promotions_u64": int(
                sum(1 for row in all_promotions if bool(row.get("activation_success_b", False)))
            ),
        },
        "accepted_promotions": all_promotions,
        "operator_bank": {
            "before_count_u64": int(before_count),
            "after_count_u64": int(after_count),
            "operators_added_u64": int(growth),
            "top10_by_usage_count": top10,
        },
        "frozen_file_hashes": {
            "all_unchanged_b": len(frozen_fail_seeds) == 0,
            "failed_seed_u64s": sorted(frozen_fail_seeds),
        },
    }

    out_path = Path(str(args.out)).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, report)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
