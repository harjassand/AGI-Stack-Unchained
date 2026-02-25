#!/usr/bin/env python3
"""Run one micdrop composite benchmark evaluation and persist the receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (REPO_ROOT, REPO_ROOT / "CDEL-v2"):
    text = str(entry)
    if text not in sys.path:
        sys.path.insert(0, text)

from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.omega import omega_benchmark_suite_composite_v1 as composite


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _normalize_budget_outcome(payload: dict[str, Any]) -> None:
    outcome = payload.get("budget_outcome")
    if not isinstance(outcome, dict):
        return
    # CPU/wall counters are runtime jitter; pin to deterministic constants.
    outcome["cpu_ms_u64"] = 0
    outcome["wall_ms_u64"] = 0
    payload["budget_outcome"] = outcome


def _stabilize_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    receipt = dict(payload)
    _normalize_budget_outcome(receipt)
    suites = receipt.get("executed_suites")
    if isinstance(suites, list):
        normalized: list[dict[str, Any]] = []
        for row in suites:
            if isinstance(row, dict):
                suite_row = dict(row)
                _normalize_budget_outcome(suite_row)
                normalized.append(suite_row)
            else:
                normalized.append(row)
        receipt["executed_suites"] = normalized
    no_id = dict(receipt)
    no_id.pop("receipt_id", None)
    receipt["receipt_id"] = canon_hash_obj(no_id)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(prog="micdrop_eval_once_v1")
    parser.add_argument("--series_prefix", default="micdrop_baseline")
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--ticks_u64", type=int, default=1)
    parser.add_argument("--seed_u64", type=int, default=7)
    args = parser.parse_args()

    pins = load_authority_pins(REPO_ROOT)
    run_receipt = composite.run_composite_once(
        repo_root=REPO_ROOT,
        runs_root=(REPO_ROOT / str(args.runs_root)).resolve(),
        series_prefix=str(args.series_prefix),
        ek_id=str(pins["active_ek_id"]),
        anchor_suite_set_id=str(pins["anchor_suite_set_id"]),
        extensions_ledger_id=str(pins["active_kernel_extensions_ledger_id"]),
        suite_runner_id=str(pins["suite_runner_id"]),
        holdout_policy_id=str(pins["holdout_policy_id"]),
        ticks_u64=int(max(1, int(args.ticks_u64))),
        seed_u64=int(max(0, int(args.seed_u64))),
    )

    stable_receipt = _stabilize_receipt(run_receipt)
    out_path = (REPO_ROOT / str(args.runs_root) / str(args.series_prefix) / "MICDROP_BENCH_RECEIPT_v2.json").resolve()
    _write_json(out_path, stable_receipt)

    summary = {
        "schema_version": "MICDROP_EVAL_ONCE_SUMMARY_v1",
        "series_prefix": str(args.series_prefix),
        "receipt_id": str(stable_receipt.get("receipt_id", "")),
        "aggregate_metrics": dict(stable_receipt.get("aggregate_metrics") or {}),
        "receipt_relpath": out_path.relative_to(REPO_ROOT).as_posix(),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
