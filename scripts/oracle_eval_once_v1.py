#!/usr/bin/env python3
"""Run one oracle holdout evaluation for a suite set."""

from __future__ import annotations

import argparse
import json
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
from tools.omega.omega_benchmark_suite_oracle_v1 import run_oracle_benchmark_once


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _find_suite_set_by_id(suite_set_id: str) -> tuple[dict[str, Any], Path]:
    suite_set_dir = (_REPO_ROOT / "authority" / "benchmark_suite_sets").resolve()
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(suite_set_dir.glob("*.json"), key=lambda p: p.as_posix()):
        payload = _load_json(path)
        if str(payload.get("schema_version", "")).strip() != "benchmark_suite_set_v1":
            continue
        if str(payload.get("suite_set_id", "")).strip() != suite_set_id:
            continue
        matches.append((payload, path))
    if not matches:
        raise RuntimeError(f"suite set id not found: {suite_set_id}")
    if len(matches) != 1:
        raise RuntimeError(f"suite set id not unique: {suite_set_id}")
    return matches[0]


def _pack_path(pack_id: str, suffix: str) -> Path:
    digest = str(pack_id).split(":", 1)[1]
    path = (_REPO_ROOT / "authority" / "holdouts" / "packs" / f"sha256_{digest}.{suffix}.json").resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"missing holdout pack: {path.relative_to(_REPO_ROOT).as_posix()}")
    return path


def _metric_q(receipt: dict[str, Any], metric_id: str) -> int:
    suites = list(receipt.get("executed_suites") or [])
    if not suites:
        return 0
    row = suites[0] if isinstance(suites[0], dict) else {}
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    metric = metrics.get(metric_id)
    if not isinstance(metric, dict):
        return 0
    return int(metric.get("q", 0))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_eval_once_v1")
    parser.add_argument("--suite_set_id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed_u64", type=int, default=0)
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--series_prefix", default="eval")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    suite_set_id = str(args.suite_set_id).strip()
    if not suite_set_id.startswith("sha256:"):
        raise ValueError("suite_set_id must be sha256:<hex64>")
    seed_u64 = _ensure_u64(int(args.seed_u64))
    ticks = max(1, int(args.ticks))

    suite_set, _suite_set_path = _find_suite_set_by_id(suite_set_id)
    suites = suite_set.get("suites")
    if not isinstance(suites, list) or not suites:
        raise RuntimeError("suite set missing suites")

    out_dir = Path(str(args.out)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    suite_rows: list[dict[str, Any]] = []
    pass_rates: list[int] = []
    coverage_rows: list[int] = []

    for ordinal, suite_entry in enumerate(suites):
        if not isinstance(suite_entry, dict):
            raise RuntimeError("suite entry must be object")
        manifest_rel = str(suite_entry.get("suite_manifest_relpath", "")).strip()
        if not manifest_rel:
            raise RuntimeError("suite manifest relpath missing")
        manifest_path = (_REPO_ROOT / manifest_rel).resolve()
        manifest = _load_json(manifest_path)

        suite_id = str(manifest.get("suite_id", "")).strip() or str(suite_entry.get("suite_id", "")).strip()
        suite_name = str(manifest.get("suite_name", "")).strip() or f"oracle_suite_{ordinal}"
        inputs_id = str(manifest.get("inputs_pack_id", "")).strip()
        hidden_id = str(manifest.get("hidden_tests_pack_id", "")).strip()
        if not inputs_id or not hidden_id:
            raise RuntimeError(f"suite missing inputs/hidden pack ids: {suite_name}")

        inputs_path = _pack_path(inputs_id, "oracle_task_inputs_pack_v1")
        hidden_path = _pack_path(hidden_id, "oracle_hidden_tests_pack_v1")

        suite_out_dir = out_dir / f"{int(ordinal):02d}_{suite_name}"
        suite_out_dir.mkdir(parents=True, exist_ok=True)

        runner_cmd = [
            sys.executable,
            str((_REPO_ROOT / "tools" / "omega" / "oracle_candidate_runner_v1.py").resolve()),
            "--mode",
            "holdout_candidate",
            "--suite_id",
            suite_id,
            "--inputs_pack_path",
            str(inputs_path),
            "--out_dir",
            str(suite_out_dir),
            "--ticks",
            str(int(ticks)),
            "--seed_u64",
            str(int(seed_u64)),
        ]
        proc = subprocess.run(runner_cmd, cwd=_REPO_ROOT, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"candidate runner failed for {suite_name}: {detail}")

        predictions_path = (suite_out_dir / "predictions.jsonl").resolve()
        if not predictions_path.exists() or not predictions_path.is_file():
            raise RuntimeError(f"predictions missing for {suite_name}")

        receipt = run_oracle_benchmark_once(
            inputs_pack_path=inputs_path,
            hidden_tests_pack_path=hidden_path,
            predictions_path=predictions_path,
            suite_id=suite_id,
            suite_name=suite_name,
            suite_set_id=suite_set_id,
        )
        write_canon_json(suite_out_dir / "ORACLE_BENCH_RECEIPT_v1.json", receipt)

        pass_rate_q32 = _metric_q(receipt, "pass_rate_q32")
        coverage_q32 = _metric_q(receipt, "coverage_q32")
        avg_ast_nodes_q32 = _metric_q(receipt, "avg_ast_nodes_q32")
        avg_eval_steps_q32 = _metric_q(receipt, "avg_eval_steps_q32")

        pass_rates.append(pass_rate_q32)
        coverage_rows.append(coverage_q32)

        suite_rows.append(
            {
                "suite_id": suite_id,
                "suite_name": suite_name,
                "pass_rate_q32": int(pass_rate_q32),
                "coverage_q32": int(coverage_q32),
                "avg_ast_nodes_q32": int(avg_ast_nodes_q32),
                "avg_eval_steps_q32": int(avg_eval_steps_q32),
                "receipt_relpath": (suite_out_dir / "ORACLE_BENCH_RECEIPT_v1.json").resolve().relative_to(_REPO_ROOT).as_posix(),
            }
        )

    summary = {
        "schema_version": "oracle_eval_once_v1",
        "suite_set_id": suite_set_id,
        "seed_u64": int(seed_u64),
        "ticks_u64": int(ticks),
        "series_prefix": str(args.series_prefix),
        "mean_pass_rate_q32": int(sum(pass_rates) // max(1, len(pass_rates))),
        "mean_coverage_q32": int(sum(coverage_rows) // max(1, len(coverage_rows))),
        "suites": suite_rows,
    }

    write_canon_json(out_dir / "ORACLE_EVAL_SUMMARY_v1.json", summary)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
