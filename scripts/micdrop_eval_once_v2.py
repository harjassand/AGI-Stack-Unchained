#!/usr/bin/env python3
"""Run one holdout evaluation for a micdrop novelty suite set."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from tools.omega.omega_benchmark_suite_composite_v1 import CompositeRunnerError, run_composite_once


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _q_metric(row: dict[str, Any], metric_id: str) -> int:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    metric = metrics.get(metric_id)
    if not isinstance(metric, dict):
        return 0
    return int(metric.get("q", 0))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="micdrop_eval_once_v2")
    parser.add_argument("--suite_set_id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed_u64", type=int, default=0)
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--series_prefix", default="eval")
    parser.add_argument("--capability_level_override", type=int, default=None)
    parser.add_argument("--holdout_policy_id", default="")
    return parser.parse_args()


def _git_ls_files_contains(relpath: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relpath],
        cwd=_REPO_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _ensure_git_ls_files_visibility(relpaths: list[str]) -> list[str]:
    added: list[str] = []
    for rel in relpaths:
        path = (_REPO_ROOT / rel).resolve()
        if not path.exists():
            continue
        already_tracked = _git_ls_files_contains(rel)
        subprocess.run(
            ["git", "add", "-N", "--", rel],
            cwd=_REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not already_tracked and _git_ls_files_contains(rel):
            added.append(rel)
    return added


def _cleanup_git_ls_files_visibility(relpaths: list[str]) -> None:
    if not relpaths:
        return
    subprocess.run(
        ["git", "reset", "--", *relpaths],
        cwd=_REPO_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    args = _parse_args()
    suite_set_id = str(args.suite_set_id).strip()
    if not suite_set_id.startswith("sha256:"):
        raise ValueError("suite_set_id must be sha256:<hex64>")
    seed_u64 = _ensure_u64(int(args.seed_u64))
    ticks_u64 = max(1, int(args.ticks))
    out_dir = Path(str(args.out)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    capability_override = args.capability_level_override
    old_override = os.environ.get("MICDROP_CAPABILITY_LEVEL_OVERRIDE")
    if capability_override is not None:
        os.environ["MICDROP_CAPABILITY_LEVEL_OVERRIDE"] = str(int(capability_override))
    temporary_index_rows = _ensure_git_ls_files_visibility(
        [
            "tools/omega/agi_micdrop_candidate_runner_v1.py",
            "tools/omega/agi_micdrop_solver_v1.py",
        ]
    )

    try:
        pins = load_authority_pins(_REPO_ROOT)
        holdout_policy_id = str(args.holdout_policy_id).strip()
        if not holdout_policy_id:
            micdrop_policy_path = _REPO_ROOT / "authority" / "holdout_policies" / "holdout_policy_micdrop_v1.json"
            if micdrop_policy_path.exists() and micdrop_policy_path.is_file():
                policy = json.loads(micdrop_policy_path.read_text(encoding="utf-8"))
                if isinstance(policy, dict):
                    candidate_id = str(policy.get("holdout_policy_id", "")).strip()
                    if candidate_id.startswith("sha256:"):
                        holdout_policy_id = candidate_id
        if not holdout_policy_id:
            holdout_policy_id = str(pins["holdout_policy_id"])
        receipt = run_composite_once(
            repo_root=_REPO_ROOT,
            runs_root=out_dir,
            series_prefix=str(args.series_prefix),
            ek_id=str(pins["active_ek_id"]),
            anchor_suite_set_id=suite_set_id,
            extensions_ledger_id=str(pins["active_kernel_extensions_ledger_id"]),
            suite_runner_id=str(pins["suite_runner_id"]),
            holdout_policy_id=holdout_policy_id,
            ticks_u64=int(ticks_u64),
            seed_u64=int(seed_u64),
        )
    except CompositeRunnerError as exc:
        print(f"INVALID:{exc.code}")
        print(f"DETAIL:{exc.detail}")
        return 1
    finally:
        _cleanup_git_ls_files_visibility(temporary_index_rows)
        if capability_override is not None:
            if old_override is None:
                os.environ.pop("MICDROP_CAPABILITY_LEVEL_OVERRIDE", None)
            else:
                os.environ["MICDROP_CAPABILITY_LEVEL_OVERRIDE"] = old_override

    executed = [row for row in list(receipt.get("executed_suites") or []) if isinstance(row, dict)]
    suite_rows: list[dict[str, Any]] = []
    for row in executed:
        suite_rows.append(
            {
                "suite_id": str(row.get("suite_id", "")),
                "suite_name": str(row.get("suite_name", "")),
                "suite_visibility": str(row.get("suite_visibility", "")),
                "suite_outcome": str(row.get("suite_outcome", "")),
                "accuracy_q32": _q_metric(row, "holdout_accuracy_q32"),
                "coverage_q32": _q_metric(row, "holdout_coverage_q32"),
            }
        )

    accuracy_rows = [int(row["accuracy_q32"]) for row in suite_rows if str(row.get("suite_visibility", "")).upper() == "HOLDOUT"]
    coverage_rows = [int(row["coverage_q32"]) for row in suite_rows if str(row.get("suite_visibility", "")).upper() == "HOLDOUT"]
    mean_accuracy_q32 = int(sum(accuracy_rows) // len(accuracy_rows)) if accuracy_rows else 0
    mean_coverage_q32 = int(sum(coverage_rows) // len(coverage_rows)) if coverage_rows else 0

    summary = {
        "schema_version": "micdrop_eval_once_v2",
        "suite_set_id": suite_set_id,
        "seed_u64": int(seed_u64),
        "ticks_u64": int(ticks_u64),
        "receipt_id": str(receipt.get("receipt_id", "")),
        "mean_accuracy_q32": int(mean_accuracy_q32),
        "mean_coverage_q32": int(mean_coverage_q32),
        "suites": suite_rows,
        "series_prefix": str(args.series_prefix),
    }
    write_canon_json(out_dir / "MICDROP_EVAL_SUMMARY_v2.json", summary)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
